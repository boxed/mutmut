from __future__ import print_function

import json
import os
import sqlite3
from subprocess import check_call, CalledProcessError, check_output
import sys
from datetime import datetime
from shutil import move, copy
from os.path import isdir, isfile
from functools import wraps

import click
from collections import defaultdict

from mutmut import mutate, ALL, count_mutations, mutate_file, Context

if sys.version_info < (3, 0):
    # noinspection PyCompatibility
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError
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
def status_printer(file):
    """
    Manage the printing and in-place updating of a line of characters.
    Note that if the string is longer than a line, then in-place
    updating may not work (it will print a new line at each refresh).
    """
    fp = file

    last_len = [0]

    def print_status(s):
        len_s = len(s)
        fp.write('\r' + s + (' ' * max(last_len[0] - len_s, 0)))
        fp.flush()
        last_len[0] = len_s
    return print_status


print_status = status_printer(sys.stdout)


@click.command()
@click.argument('paths_to_mutate', nargs=-1)
@click.option('--apply', help='apply the mutation to the given file. Must be used in combination with --mutation_number', is_flag=True)
@click.option('--backup/--no-backup', default=False)
@click.option('--mutation')
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
    if mutation is not None:
        mutation = int(mutation)  # click.INT parses "0" as None

    if paths_to_mutate is None:
        # Guess path with code
        this_dir = os.getcwd().split(os.sep)[-1]
        if isdir('lib'):
            paths_to_mutate = 'lib'
        elif isdir('src'):
            paths_to_mutate = 'src'
        elif isdir(this_dir):
            paths_to_mutate = this_dir
        else:
            print('Could not figure out where the code to mutate is. Please specify it on the command line like "mutmut code_dir" or by adding "paths_to_mutate=code_dir" in setup.cfg under the section [mutmut]')
            return

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        print('You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')
        return

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    if apply:
        assert mutation is not None
        assert len(paths_to_mutate) == 1
        mutations_performed = mutate_file(
            backup=backup,
            context=Context(
                mutate_index=mutation,
                filename=paths_to_mutate[0],
                dict_synonyms=dict_synonyms,
            ),
        )
        if mutations_performed == 0:
            print('ERROR: no mutations performed. Are you sure the index is not too big?')
        return

    null_stdout = open(os.devnull, 'w') if not s else None
    null_stderr = open(os.devnull, 'w') if not s else None

    test_command = '%s %s' % (runner, tests_dir)

    using_testmon = '--testmon' in test_command

    def run_tests():
        if using_testmon:
            copy('.testmondata-initial', '.testmondata')
        check_call(test_command, shell=True, stdout=null_stdout, stderr=null_stderr)

    start_time = datetime.now()
    try:
        check_output(test_command, shell=True)
        baseline_time_elapsed = datetime.now() - start_time
    except CalledProcessError as e:
        if using_testmon and e.returncode == 5:
            baseline_time_elapsed = datetime.now() - start_time
        else:
            print("Tests don't run cleanly without mutations. Test command was: %s" % test_command)
            print(e.output.decode())
            return

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    coverage_data = None
    if use_coverage:
        print('Using coverage data from .coverage file')
        # noinspection PyPackageRequirements
        import coverage
        coverage_data = coverage.CoverageData()
        coverage_data.read_file('.coverage')

    # Cache file
    db = sqlite3.connect('.mutmut_db.sqlite', isolation_level=None)
    db_cursor = db.cursor()
    db_cursor.execute('CREATE TABLE IF NOT EXISTS surviving_mutants (filename TEXT, path TEXT)')
    skip_based_on_previous_information_by_filename = defaultdict(set)
    for filename, path in db_cursor.execute('SELECT filename, path FROM surviving_mutants'):
        skip_based_on_previous_information_by_filename[filename].add((filename,) + tuple(json.loads(path)))
    if skip_based_on_previous_information_by_filename:
        print('Skipping mutation on some lines, due to cached information in `.mutmut_db.sqlite`. If you want to run a full mutation testing run, please delete this file and restart mutmut.')

    #
    def exclude(context):
        if use_coverage:
            measured_lines = coverage_data.lines(os.path.abspath(context.filename))
            if measured_lines is None:
                return True
            if context.current_line not in measured_lines:
                return True

        if context.filename in skip_based_on_previous_information_by_filename:
            if context.path_by_line_number[context.current_line] in skip_based_on_previous_information_by_filename[filename]:
                return True

        return False

    mutations_by_file = {}

    def add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms):
        mutations_by_file[filename] = count_mutations(
            Context(
                source=open(filename).read(),
                filename=filename,
                exclude=exclude,
                dict_synonyms=dict_synonyms,
            )
        )

    for path in paths_to_mutate:
        if isfile(path) and path.endswith('.py'):
            filename = path
            add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms)
        else:
            for filename in python_source_files(path):
                add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms)

    total = sum(mutations_by_file.values())

    print('--- starting mutation ---')
    progress = 0

    for filename, mutations in mutations_by_file.items():
        context = Context(
            filename=filename,
            exclude=exclude,
            dict_synonyms=dict_synonyms,
            db_cursor=db_cursor,
        )

        last_line_number = 0

        for mutation_index in range(mutations):
            if mutation is not None and mutation != mutation_index:
                continue

            context.mutate_index = mutation_index

            start_time = datetime.now()
            progress += 1
            print_status('%s out of %s  (file: %s, mutation: %s)' % (progress, total, filename, mutation_index))
            try:
                apply_line = 'mutmut %s --mutation %s --apply' % (filename, mutation_index)
                assert mutate_file(
                    backup=True,
                    context=context,
                )
                try:
                    run_tests()
                    print_status('')
                    time_elapsed = (datetime.now() - start_time)
                    print('\rFAILED: %s' % apply_line)
                    # print(check_output(['/usr/local/bin/git', 'diff']))

                    # Surviving mutant!
                    assert len(context.performed_mutations_line_numbers) == 1
                    context.surviving_mutants_by_line_number[context.performed_mutations_line_numbers[0]] += 1

                except CalledProcessError as e:
                    if using_testmon and e.returncode == 5:
                        print('\rFAILED (all tests skipped, uncovered line?): %s' % apply_line)
                    time_elapsed = (datetime.now() - start_time)

                if time_elapsed > baseline_time_elapsed * 2:
                    print('\nSUSPICIOUS LONG TIME: %s > expected %s (%s)' % (time_elapsed, baseline_time_elapsed, apply_line))
                os.remove(filename)
                try:
                    os.remove(filename+'c')  # remove .pyc file
                except OSError:
                    pass
            finally:
                context.save_progress()

                try:
                    move(filename+'.bak', filename)

                    if show_times:
                        print('time: %s' % time_elapsed)
                except IOError:
                    pass

            if last_line_number != context.current_line:
                if last_line_number not in context.surviving_mutants_by_line_number:
                    # Record a line that had zero surviving mutants
                    context.surviving_mutants_by_line_number[last_line_number] = 0
            last_line_number = context.current_line

        context.save_progress()


def python_source_files(path):
    if isdir(path):
        for root, dirs, files in os.walk(path):
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def number_of_mutations(path):
    total = 0
    for filename in python_source_files(path):
        _, c = mutate(Context(source=open(filename).read(), mutate_index=ALL))
        total += c
    return total


if __name__ == '__main__':
    main()
