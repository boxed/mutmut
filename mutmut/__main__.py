#!/usr/bin/python
# -*- coding: utf-8 -*-

"""main entrypoint for mutmut"""

from __future__ import print_function

import os
import sys
from difflib import unified_diff
from functools import wraps
from io import open
from shutil import copy

import click
from glob2 import glob

from mutmut import __version__
from mutmut.cache import print_result_cache, update_line_numbers, \
    get_filename_and_mutation_id_from_pk, hash_of_tests
from mutmut.file_collection import python_source_files, read_coverage_data, \
    get_or_guess_paths_to_mutate
from mutmut.mutators import Context, mutate
from mutmut.runner import run_mutation_tests, Config, do_apply, \
    time_test_suite, add_mutations_by_file

if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    # noinspection PyCompatibility,PyUnresolvedReferences
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError  # pylint: disable=import-error
    # This little hack is needed to get the click tester working on python 2.7
    orig_print = print

    def print(x='', **kwargs):
        orig_print(x.encode('utf8'), **kwargs)
else:
    # noinspection PyUnresolvedReferences,PyCompatibility
    from configparser import ConfigParser, NoOptionError, NoSectionError

START_MESSAGE = """
- Mutation testing starting - 

These are the steps:
1. A full test suite run will be made to make sure we 
   can run the tests successfully and we know how long 
   it takes (to detect infinite loops for example)
2. Mutants will be generated and checked

Mutants are written to the cache in the .mutmut-cache 
directory. Print found mutants with `mutmut results`.

Legend for output:
🎉 Killed mutants. The goal is for everything to end up in this bucket. 
⏰ Timeout. Test suite took 10 times as long as the baseline so were killed.  
🤔 Suspicious. Tests took a long time, but not long enough to be fatal. 
🙁 Survived. This means your tests needs to be expanded. 
"""


def config_from_setup_cfg(**defaults):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            config_parser = ConfigParser()
            config_parser.read('setup.cfg')

            def s(key, default):
                try:
                    return config_parser.get('mutmut', key)
                except (NoOptionError, NoSectionError):
                    return default

            for k in list(kwargs.keys()):
                if not kwargs[k]:
                    kwargs[k] = s(k, defaults.get(k))
            func(*args, **kwargs)

        return wrapper
    return decorator


null_out = open(os.devnull, 'w')

DEFAULT_TESTS_DIR = 'tests/:test/'


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('command', nargs=1, required=False)
@click.argument('argument', nargs=1, required=False)
@click.option('--paths-to-mutate', type=click.STRING)
@click.option('--backup/--no-backup', default=False)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--tests-dir')
@click.option('-s', help='turn off output capture', is_flag=True)
@click.option('--dict-synonyms')
@click.option('--cache-only', is_flag=True, default=False)
@click.option('--version', is_flag=True, default=False)
@config_from_setup_cfg(
    dict_synonyms='',
    runner='python -m pytest -x',
    tests_dir=DEFAULT_TESTS_DIR,
)
def main(command, argument, paths_to_mutate, backup, runner, tests_dir, s,
         use_coverage, dict_synonyms, cache_only, version):
    """
commands:\n
    run [mutation id]\n
        Runs mutmut. You probably want to start with just trying this.
        If you supply a mutation ID mutmut will check just this mutant.\n
    results\n
        Print the results.\n
    apply [mutation id]\n
        Apply a mutation on disk.\n
    show [mutation id]\n
        Show a mutation diff.\n

    :return: return code of running mutmut
    :rtype: int
    """
    if version:
        print("mutmut version %s" % __version__)
        return 0

    valid_commands = ['run', 'results', 'apply', 'show']
    if command not in valid_commands:
        raise ValueError('%s is not a valid command, must be one of %s' % (command, ', '.join(valid_commands)))

    if command == 'results' and argument:
        raise ValueError('The %s command takes no arguments' % command)

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if command in ('show', 'diff'):
        if not argument:
            print_result_cache()
            return 0

        filename, mutation_id = \
            get_filename_and_mutation_id_from_pk(int(argument))
        with open(filename) as f:
            source = f.read()
        context = Context(
            source=source,
            filename=filename,
            mutation_id=mutation_id,
            dict_synonyms=dict_synonyms,
        )
        mutated_source, number_of_mutations_performed = mutate(context)
        if not number_of_mutations_performed:
            raise ValueError('No mutations performed')

        for line in unified_diff(source.split('\n'), mutated_source.split('\n'), fromfile=filename, tofile=filename, lineterm=''):
            print(line)

        return 0

    if use_coverage and not os.path.exists('.coverage'):
        raise FileNotFoundError(
            'No .coverage file found. You must generate a coverage '
            'file to use this feature.'
        )

    if command == 'results':
        print_result_cache()
        return 0

    if command == 'apply':
        do_apply(argument, dict_synonyms, backup)
        return 0

    if paths_to_mutate is None:
        paths_to_mutate = get_or_guess_paths_to_mutate()

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [path.strip() for path in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise FileNotFoundError(
            'You must specify a list of paths to mutate. '
            'Either as a command line argument, or by setting paths_to_mutate '
            'under the section [mutmut] in setup.cfg'
        )

    tests_dirs = []
    for p in tests_dir.split(':'):
        tests_dirs.extend(glob(p, recursive=True))

    for p in paths_to_mutate:
        for pt in tests_dir.split(':'):
            tests_dirs.extend(glob(p + '/**/' + pt, recursive=True))
    del tests_dir

    # stop python from creating .pyc files
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

    using_testmon = '--testmon' in runner

    print(START_MESSAGE)

    baseline_time_elapsed = time_test_suite(
        swallow_output=not s,
        test_command=runner,
        using_testmon=using_testmon
    )

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    if not use_coverage:
        def _exclude(context):
            return False
    else:
        covered_lines_by_filename = {}
        coverage_data = read_coverage_data()

        def _exclude(context):
            try:
                covered_lines = covered_lines_by_filename[context.filename]
            except KeyError:
                covered_lines = coverage_data.lines(
                    os.path.abspath(context.filename))
                covered_lines_by_filename[context.filename] = covered_lines

            if covered_lines is None:
                return True
            current_line = context.current_line_index + 1
            if current_line not in covered_lines:
                return True
            return False

    assert command == 'run'

    mutations_by_file = {}

    if argument is None:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs):
                update_line_numbers(filename)
                add_mutations_by_file(mutations_by_file, filename, _exclude,
                                      dict_synonyms)
    else:
        filename, mutation_id = \
            get_filename_and_mutation_id_from_pk(int(argument))
        mutations_by_file[filename] = [mutation_id]

    total = sum(len(mutations) for mutations in mutations_by_file.values())

    print('2. Checking mutants')
    config = Config(
        swallow_output=not s,
        test_command=runner,
        exclude_callback=_exclude,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=backup,
        dict_synonyms=dict_synonyms,
        total=total,
        using_testmon=using_testmon,
        cache_only=cache_only,
        tests_dirs=tests_dirs,
        hash_of_tests=hash_of_tests(tests_dirs),
    )

    run_mutation_tests(config=config, mutations_by_file=mutations_by_file)
    return 0


if __name__ == '__main__':
    sys.exit(main())  # pylint: disable=no-value-for-parameter
