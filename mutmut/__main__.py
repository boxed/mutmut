from __future__ import print_function

import os
from subprocess import check_call, CalledProcessError, check_output

import click
import sys

from datetime import datetime

from os.path import isdir, dirname

from mutmut import mutate, ALL, count_mutations, mutate_file, config_from_setup_cfg
from shutil import move, copy


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
@click.option('--mutation', type=click.INT)
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

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if not paths_to_mutate:
        print('You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')
        return

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    if apply:
        assert mutation is not None
        assert len(paths_to_mutate) == 1
        mutations_performed = mutate_file(backup, mutation, paths_to_mutate[0])
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
        import coverage
        coverage_data = coverage.CoverageData()
        coverage_data.read_file('.coverage')

    def exclude(context):
        if use_coverage:
            measured_lines = coverage_data.lines(os.path.abspath(context.filename))
            if measured_lines is None:
                return True
            if context.current_line not in measured_lines:
                return True

        return False

    mutations_by_file = {}

    for path in paths_to_mutate:
        for filename in python_source_files(path):
            mutations_by_file[filename] = count_mutations(open(filename).read(), context__filename=filename, context__exclude=exclude)

    total = sum(mutations_by_file.values())

    print('--- starting mutation ---')
    progress = 0
    for filename, mutations in mutations_by_file.items():
        for mutation_index in range(mutations):
            if mutation is not None and mutation != mutation_index:
                continue
            start_time = datetime.now()
            progress += 1
            print_status('%s out of %s  (file: %s, mutation: %s)' % (progress, total, filename, mutation_index))
            try:
                apply_line = 'mutmut %s --mutation %s --apply' % (filename, mutation_index)
                assert mutate_file(
                    backup=True,
                    mutation=mutation_index,
                    filename=filename,
                    context__exclude=exclude,
                    context__dict_synonyms=dict_synonyms,
                )
                try:
                    run_tests()
                    print_status('')
                    time_elapsed = (datetime.now() - start_time)
                    print('\rFAILED: %s' % apply_line)
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
                try:
                    move(filename+'.bak', filename)

                    if show_times:
                        print('time: %s' % time_elapsed)
                except IOError:
                    pass


def python_source_files(path):
    for root, dirs, files in os.walk(path):
        for filename in files:
            if filename.endswith('.py'):
                yield os.path.join(root, filename)


def number_of_mutations(path):
    total = 0
    for filename in python_source_files(path):
        _, c = mutate(open(filename).read(), ALL)
        total += c
    return total


if __name__ == '__main__':
    main()
