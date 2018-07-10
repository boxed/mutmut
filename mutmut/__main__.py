# coding=utf-8
from __future__ import print_function

import os
from subprocess import check_call, CalledProcessError, check_output
import sys
from datetime import datetime
from shutil import move, copy
from os.path import isdir
from functools import wraps

import click

from . import mutate_file, Context, list_mutations

if sys.version_info < (3, 0):
    # noinspection PyCompatibility
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError
    # This little hack is needed to get the click tester working on python 2.7
    orig_print = print
    print = lambda x: orig_print(x.encode('utf8'))
else:
    # noinspection PyUnresolvedReferences
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


# this function is stolen and modified from tqdm
def status_printer():
    """
    Manage the printing and in-place updating of a line of characters.
    Note that if the string is longer than a line, then in-place
    updating may not work (it will print a new line at each refresh).
    """
    last_len = [0]

    def p(s):
        len_s = len(s)
        sys.stdout.write('\r' + s + (' ' * max(last_len[0] - len_s, 0)))
        sys.stdout.flush()
        last_len[0] = len_s
    return p


print_status = status_printer()


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
            raise ErrorMessage('Could not figure out where the code to mutate is. Please specify it on the command line like "mutmut code_dir" or by adding "paths_to_mutate=code_dir" in setup.cfg under the section [mutmut]')
    else:
        return paths_to_mutate


mutation_id_separator = u'⤑'


def do_apply(mutation, paths_to_mutate, dict_synonyms, backup):
    assert mutation is not None

    mutation_id = mutation.split(mutation_id_separator)
    mutation_id[1] = int(mutation_id[1])
    mutation_id = tuple(mutation_id)

    assert len(paths_to_mutate) == 1
    context = Context(
        mutate_id=mutation_id,
        filename=paths_to_mutate[0],
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )
    if context.number_of_performed_mutations == 0:
        raise ErrorMessage('ERROR: no mutations performed. Are you sure the index is not too big?')


class ErrorMessage(Exception):
    pass


@click.command()
@click.argument('paths_to_mutate', nargs=-1)
@click.option('--apply', help='apply the mutation to the given file. Must be used in combination with --mutation_number', is_flag=True)
@click.option('--backup/--no-backup', default=False)
@click.option('--mutation', type=click.STRING)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--tests-dir')
@click.option('-s', help='turn off output capture', is_flag=True)
@click.option('--show-times', help='show times for each mutation', is_flag=True)
@click.option('--dict-synonyms')
@config_from_setup_cfg(
    dict_synonyms='',
    runner='python -m pytest -x',
    tests_dir='tests/',
    show_times=False,
)
def main(paths_to_mutate, apply, mutation, backup, runner, tests_dir, s, use_coverage, dict_synonyms, show_times):
    paths_to_mutate = get_or_guess_paths_to_mutate(paths_to_mutate)

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise ErrorMessage('You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    if apply:
        do_apply(mutation, paths_to_mutate, dict_synonyms, backup)
        return

    del mutation

    null_stdout = open(os.devnull, 'w') if not s else None
    null_stderr = open(os.devnull, 'w') if not s else None

    test_command = '%s %s' % (runner, tests_dir)

    using_testmon = '--testmon' in test_command

    def run_tests():
        if using_testmon:
            copy('.testmondata-initial', '.testmondata')
        check_call(test_command, shell=True, stdout=null_stdout, stderr=null_stderr)

    baseline_time_elapsed = time_test_suite(test_command, using_testmon)

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    coverage_data = read_coverage_data(use_coverage)

    mutations_by_file = {}

    def _exclude(context):
        return exclude_callback(context=context, use_coverage=use_coverage, coverage_data=coverage_data)

    for path in paths_to_mutate:
        for filename in python_source_files(path):
            add_mutations_by_file(mutations_by_file, filename, _exclude, dict_synonyms)

    total = sum(len(mutations) for mutations in mutations_by_file.values())

    print('--- starting mutation ---')
    progress = 0
    for filename, mutations in mutations_by_file.items():
        for mutation_id in mutations:
            if mutation_id is not None and mutation_id != mutation_id:
                continue
            start_time = datetime.now()
            progress += 1
            print_status('%s out of %s  (file: %s)' % (progress, total, filename))
            time_elapsed = None
            try:
                apply_line = 'mutmut %s --mutation "%s%s%s" --apply' % (filename, mutation_id[0].replace('"', '\\"'), mutation_id_separator, mutation_id[1])
                context = Context(
                    mutate_id=mutation_id,
                    filename=filename,
                    exclude=_exclude,
                    dict_synonyms=dict_synonyms,
                )
                assert mutate_file(
                    backup=True,
                    context=context
                )
                try:
                    run_tests()
                    print_status('')
                    time_elapsed = (datetime.now() - start_time)
                    print('\rFAILED: %s' % apply_line)
                except CalledProcessError as e:
                    if using_testmon and e.returncode == 5:
                        print('\rFAILED (all tests skipped, uncovered line?)\n   %s' % apply_line)
                    time_elapsed = (datetime.now() - start_time)

                if time_elapsed > baseline_time_elapsed * 2:
                    print('\nSUSPICIOUS LONG TIME: %s > expected %s\n   %s' % (time_elapsed, baseline_time_elapsed, apply_line))
                os.remove(filename)
                try:
                    os.remove(filename+'c')  # remove .pyc file
                except OSError:
                    pass
            finally:
                try:
                    move(filename+'.bak', filename)

                    if show_times:
                        print('time: %s' % time_elapsed)
                except IOError:
                    pass


def read_coverage_data(use_coverage):
    if use_coverage:
        print('Using coverage data from .coverage file')
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        import coverage
        coverage_data = coverage.CoverageData()
        coverage_data.read_file('.coverage')
        return coverage_data
    else:
        return None


def time_test_suite(test_command, using_testmon):
    start_time = datetime.now()
    try:
        check_output(test_command, shell=True)
        baseline_time_elapsed = datetime.now() - start_time
    except CalledProcessError as e:
        if using_testmon and e.returncode == 5:
            baseline_time_elapsed = datetime.now() - start_time
        else:
            raise ErrorMessage("Tests don't run cleanly without mutations. Test command was: %s\n\n%s" % (test_command, e.output.decode()))
    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms):
    mutations_by_file[filename] = list_mutations(
        Context(
            source=open(filename).read(),
            filename=filename,
            exclude=exclude,
            dict_synonyms=dict_synonyms,
        )
    )


def exclude_callback(context, use_coverage, coverage_data):
    if use_coverage:
        measured_lines = coverage_data.lines(os.path.abspath(context.filename))
        if measured_lines is None:
            return True
        if context.current_line not in measured_lines:
            return True

    return False


def python_source_files(path):
    if isdir(path):
        for root, dirs, files in os.walk(path):
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


if __name__ == '__main__':
    try:
        main()
    except ErrorMessage as main_error:
        print(str(main_error))
