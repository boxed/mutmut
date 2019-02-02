#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from functools import wraps
from io import open
from os.path import isdir, exists
from shutil import copy

import click
from glob2 import glob

from mutmut import __version__, print
from mutmut.cache import print_result_cache, \
    filename_and_mutation_id_from_pk, print_result_cache_junitxml, \
    get_unified_diff, register_mutants, hash_of_tests, update_line_numbers
from mutmut.mutator import Mutator
from mutmut.runner import time_test_suite, Runner, compute_exit_code

if sys.version_info < (3, 0):  # pragma: no cover (python 2 specific)
    # noinspection PyCompatibility,PyUnresolvedReferences
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError
else:
    # noinspection PyUnresolvedReferences,PyCompatibility
    from configparser import ConfigParser, NoOptionError, NoSectionError


# decorator
def config_from_setup_cfg(**defaults):
    def decorator(f):
        @wraps(f)
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
            f(*args, **kwargs)

        return wrapper

    return decorator


def get_or_guess_paths_to_mutate(paths_to_mutate):
    if paths_to_mutate is None:
        # Guess path with code
        this_dir = os.getcwd().split(os.sep)[-1]
        if isdir('lib'):
            return 'lib'
        elif isdir('src'):
            return 'src'
        elif isdir(this_dir):
            return this_dir
        else:
            raise FileNotFoundError(
                'Could not figure out where the code to mutate is. '
                'Please specify it on the command line like "mutmut code_dir" '
                'or by adding "paths_to_mutate=code_dir" in setup.cfg under '
                'the section [mutmut]')
    else:
        return paths_to_mutate


def do_apply(mutation_pk, dict_synonyms, backup):
    """Apply a specified mutant to the source code"""
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))
    for mutant in Mutator(mutation_id=mutation_id, filename=filename,
                          dict_synonyms=dict_synonyms).yield_mutants():
        mutant.apply(backup)
    # # TODO: apply mutant
    # if context.number_of_performed_mutations == 0:
    #     raise RuntimeError(
    #         'No mutations performed. Are you sure the index is not too big?')


NULL_OUT = open(os.devnull, 'w')

DEFAULT_TESTS_DIR = 'tests/:test/'


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('command', nargs=1, required=False)
@click.argument('argument', nargs=1, required=False)
@click.option('--paths-to-mutate', type=click.STRING)
@click.option('--backup/--no-backup', default=False)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--tests-dir')
@click.option('-m', '--test-time-multiplier', default=2.0, type=float)
@click.option('-b', '--test-time-base', default=0.0, type=float)
@click.option('-s', '--swallow-output', help='turn off output capture',
              is_flag=True)
@click.option('--dict-synonyms')
@click.option('--cache-only', is_flag=True, default=False)
@click.option('--version', is_flag=True, default=False)
@click.option('--suspicious-policy',
              type=click.Choice(['ignore', 'skipped', 'error', 'failure']),
              default='ignore')
@click.option('--untested-policy',
              type=click.Choice(['ignore', 'skipped', 'error', 'failure']),
              default='ignore')
@config_from_setup_cfg(
    dict_synonyms='',
    runner='python -m pytest -x',
    tests_dir=DEFAULT_TESTS_DIR,
)
def climain(command, argument, paths_to_mutate, backup, runner, tests_dir,
            test_time_multiplier, test_time_base,
            swallow_output, use_coverage, dict_synonyms, cache_only, version,
            suspicious_policy, untested_policy):
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
    """
    if test_time_base is None:  # click sets the default=0.0 to None
        test_time_base = 0.0
    if test_time_multiplier is None:  # click sets the default=0.0 to None
        test_time_multiplier = 0.0
    sys.exit(main(command, argument, paths_to_mutate, backup, runner,
                  tests_dir, test_time_multiplier, test_time_base,
                  swallow_output, use_coverage, dict_synonyms, cache_only,
                  version, suspicious_policy, untested_policy))


def main(command, argument, paths_to_mutate, backup, runner, tests_dir,
         test_time_multiplier, test_time_base,
         swallow_output, use_coverage, dict_synonyms, cache_only, version,
         suspicious_policy,
         untested_policy):
    """return exit code, after performing an mutation test run.

    :return: the exit code from executing the mutation tests
    :rtype: int
    """
    if version:
        print("mutmut version %s" % __version__)
        return 0

    valid_commands = ['run', 'results', 'apply', 'show', 'junitxml']
    if command not in valid_commands:
        raise click.BadArgumentUsage(
            '%s is not a valid command, must be one of %s' % (
            command, ', '.join(valid_commands)))

    if command == 'results' and argument:
        raise click.BadArgumentUsage(
            'The %s command takes no arguments' % command)

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if command in ('show', 'diff'):
        if not argument:
            print_result_cache()
            return 0

        print(get_unified_diff(argument, dict_synonyms))
        return 0

    if use_coverage and not exists('.coverage'):
        raise FileNotFoundError(
            'No .coverage file found. You must generate a coverage file '
            'to use this feature.')

    if command == 'results':
        print_result_cache()
        return 0

    if command == 'junitxml':
        print_result_cache_junitxml(dict_synonyms, suspicious_policy,
                                    untested_policy)
        return 0

    if command == 'apply':
        do_apply(argument, dict_synonyms, backup)
        return 0

    paths_to_mutate = get_or_guess_paths_to_mutate(paths_to_mutate)

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise click.BadOptionUsage(
            '--paths-to-mutate',
            'You must specify a list of paths to mutate. Either as a command '
            'line argument, or by setting paths_to_mutate under the '
            'section [mutmut] in setup.cfg')

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

    print("""
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
""")
    baseline_time_elapsed = time_test_suite(
        swallow_output=not swallow_output,
        test_command=runner,
        using_testmon=using_testmon
    )

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    if not use_coverage:
        def _exclude(mutator):
            return False
    else:
        covered_lines_by_filename = {}
        coverage_data = read_coverage_data(use_coverage)

        def _exclude(mutator):
            try:
                covered_lines = covered_lines_by_filename[mutator.filename]
            except KeyError:
                covered_lines = coverage_data.lines(
                    os.path.abspath(mutator.filename))
                covered_lines_by_filename[mutator.filename] = covered_lines

            if covered_lines is None:
                return True
            current_line = mutator.current_line_index + 1
            if current_line not in covered_lines:
                return True
            return False

    if command != 'run':
        raise click.BadArgumentUsage("Invalid command %s" % command)

    mutants = []
    for path in paths_to_mutate:
        for filename in python_source_files(path, tests_dirs):
            update_line_numbers(filename)
            for mutant in Mutator(filename=filename,
                                  exclude=_exclude).yield_mutants():
                mutants.append(mutant)
    print("generated {} mutants".format(len(mutants)))
    register_mutants(mutants)
    # run the mutants
    mutation_test_runner = Runner(
        test_command=runner,
        test_time_base=test_time_base,
        test_time_multiplier=test_time_multiplier,
        hash_of_tests=hash_of_tests(tests_dirs),
        using_testmon=using_testmon,
        swallow_output=not swallow_output,
        baseline_test_time=baseline_time_elapsed
    )

    mutation_test_runner.run_mutation_tests(mutants)
    return compute_exit_code(mutants)


def read_coverage_data(use_coverage):
    if use_coverage:
        print('Using coverage data from .coverage file')
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        from coverage import Coverage
        cov = Coverage('.coverage')
        cov.load()
        return cov.get_data()
    else:
        return None


def python_source_files(path, tests_dirs):
    """Attempt to guess where the python source files to mutate are and yield
    their paths

    :param path: path to a python source file or package directory
    :type path: str

    :param tests_dirs: list of directory paths containing test files
        (we do not want to mutate these!)
    :type tests_dirs: list[str]

    :return: generator listing the paths to the python source files to mutate
    :rtype: Generator[str, None, None]
    """
    if isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if
                       os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


if __name__ == '__main__':
    climain()
