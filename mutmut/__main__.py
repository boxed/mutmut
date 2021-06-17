#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import traceback
from io import (
    open,
)
from os.path import exists
from shutil import copy
from time import time

import click
from glob2 import glob

from mutmut import (
    mutate_file,
    Context,
    __version__,
    mutmut_config,
    config_from_setup_cfg,
    guess_paths_to_mutate,
    Config,
    Progress,
    check_coverage_data_filepaths,
    popen_streaming_output,
    run_mutation_tests,
    read_coverage_data,
    read_patch_data,
    add_mutations_by_file,
    python_source_files,
    compute_exit_code,
    print_status,
    close_active_queues,
)
from mutmut.cache import (
    create_html_report,
    cached_hash_of_tests,
)
from mutmut.cache import print_result_cache, \
    hash_of_tests, \
    filename_and_mutation_id_from_pk, cached_test_time, set_cached_test_time, \
    update_line_numbers, print_result_cache_junitxml, get_unified_diff
    
from collections import namedtuple
import re

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())


def do_apply(mutation_pk, dict_synonyms, backup):
    """Apply a specified mutant to the source code

    :param mutation_pk: mutmut cache primary key of the mutant to apply
    :type mutation_pk: str

    :param dict_synonyms: list of synonym keywords for a python dictionary
    :type dict_synonyms: list[str]

    :param backup: if :obj:`True` create a backup of the source file
        before applying the mutation
    :type backup: bool
    """
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))

    update_line_numbers(filename)

    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )


null_out = open(os.devnull, 'w')

DEFAULT_RUNNER = 'python -m pytest -x --assert=plain'

@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('command', nargs=1, required=False)
@click.argument('argument', nargs=1, required=False)
@click.argument('argument2', nargs=1, required=False)
@click.option('--paths-to-mutate', type=click.STRING)
@click.option('--paths-to-exclude', type=click.STRING, required=False)
@click.option('--backup/--no-backup', default=False)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--use-patch-file', help='Only mutate lines added/changed in the given patch file')
@click.option('--tests-dir')
@click.option('-m', '--test-time-multiplier', default=2.0, type=float)
@click.option('-b', '--test-time-base', default=0.0, type=float)
@click.option('-s', '--swallow-output', help='turn off output capture', is_flag=True)
@click.option('--dict-synonyms')
@click.option('--cache-only', is_flag=True, default=False)
@click.option('--version', is_flag=True, default=False)
@click.option('--suspicious-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@click.option('--untested-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@click.option('--pre-mutation')
@click.option('--post-mutation')
@click.option('--simple-output', is_flag=True, default=False, help="Swap emojis in mutmut output to plain text alternatives.")
@click.option('--no-progress', is_flag=True, default=False, help="Disable real-time progress indicator")
@config_from_setup_cfg(
    dict_synonyms='',
    paths_to_exclude='',
    runner=DEFAULT_RUNNER,
    tests_dir='tests/:test/',
    pre_mutation=None,
    post_mutation=None,
    use_patch_file=None,
)
def climain(command, argument, argument2, paths_to_mutate, backup, runner, tests_dir,
            test_time_multiplier, test_time_base,
            swallow_output, use_coverage, dict_synonyms, cache_only, version,
            suspicious_policy, untested_policy, pre_mutation, post_mutation,
            use_patch_file, paths_to_exclude, simple_output, no_progress):
    """
commands:\n
    run [mutation id]\n
        Runs mutmut. You probably want to start with just trying this. If you supply a mutation ID mutmut will check just this mutant.\n
    results\n
        Print the results.\n
    apply [mutation id]\n
        Apply a mutation on disk.\n
    show [mutation id]\n
        Show a mutation diff.\n
    show [path to file]\n
        Show all mutation diffs for this file.\n
    junitxml\n
        Show a mutation diff with junitxml format.
    """
    if test_time_base is None:  # click sets the default=0.0 to None
        test_time_base = 0.0
    if test_time_multiplier is None:  # click sets the default=0.0 to None
        test_time_multiplier = 0.0
    sys.exit(main(command, argument, argument2, paths_to_mutate, backup, runner,
                  tests_dir, test_time_multiplier, test_time_base,
                  swallow_output, use_coverage, dict_synonyms, cache_only,
                  version, suspicious_policy, untested_policy, pre_mutation,
                  post_mutation, use_patch_file, paths_to_exclude, simple_output,
                  no_progress))


def main(command, argument, argument2, paths_to_mutate, backup, runner, tests_dir,
         test_time_multiplier, test_time_base,
         swallow_output, use_coverage, dict_synonyms, cache_only, version,
         suspicious_policy, untested_policy, pre_mutation, post_mutation,
         use_patch_file, paths_to_exclude, simple_output, no_progress):
    """return exit code, after performing an mutation test run.

    :return: the exit code from executing the mutation tests
    :rtype: int
    """
    if version:
        print("mutmut version {}".format(__version__))
        return 0

    if use_coverage and use_patch_file:
        raise click.BadArgumentUsage("You can't combine --use-coverage and --use-patch")

    valid_commands = ['run', 'results', 'apply', 'show', 'junitxml', 'html']
    if command not in valid_commands:
        raise click.BadArgumentUsage('{} is not a valid command, must be one of {}'.format(command, ', '.join(valid_commands)))

    if command == 'results' and argument:
        raise click.BadArgumentUsage('The {} command takes no arguments'.format(command))

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if command in ('show', 'diff'):
        if not argument:
            print_result_cache()
            return 0

        if argument == 'all':
            print_result_cache(show_diffs=True, dict_synonyms=dict_synonyms, print_only_filename=argument2)
            return 0

        if os.path.isfile(argument):
            print_result_cache(show_diffs=True, only_this_file=argument)
            return 0

        print(get_unified_diff(argument, dict_synonyms))
        return 0

    if use_coverage and not exists('.coverage'):
        raise FileNotFoundError('No .coverage file found. You must generate a coverage file to use this feature.')

    if command == 'results':
        print_result_cache()
        return 0

    if command == 'junitxml':
        print_result_cache_junitxml(dict_synonyms, suspicious_policy, untested_policy)
        return 0

    if command == 'html':
        create_html_report(dict_synonyms)
        return 0

    if command == 'apply':
        do_apply(argument, dict_synonyms, backup)
        return 0

    if paths_to_mutate is None:
        paths_to_mutate = guess_paths_to_mutate()

    Pattern = namedtuple('Pattern', 'char pattern')

    def get_pattern(char):
        return re.compile(fr"^(\w+)({char}\s*\w+)*$")

    def get_separation_char(input_string, patterns):
        for p in patterns:
            if p.pattern.match(input_string):
                return p.char

    patterns = [Pattern(',', get_pattern(',')),
                Pattern(':', get_pattern(':'))]

    mut_paths_sep = get_separation_char(paths_to_mutate, patterns)
    tests_dir_sep = get_separation_char(tests_dir, patterns)

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(mut_paths_sep)]

    if not paths_to_mutate:
        raise click.BadOptionUsage('--paths-to-mutate', 'You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')

    tests_dirs = []
    for p in tests_dir.split(tests_dir_sep):
        tests_dirs.extend(glob(p, recursive=True))

    for p in paths_to_mutate:
        for pt in tests_dir.split(tests_dir_sep):
            tests_dirs.extend(glob(p + '/**/' + pt, recursive=True))
    del tests_dir
    current_hash_of_tests = hash_of_tests(tests_dirs)

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    using_testmon = '--testmon' in runner
    output_legend = {
        "killed": "🎉",
        "timeout": "⏰",
        "suspicious": "🤔",
        "survived": "🙁",
        "skipped": "🔇",
    }
    if simple_output:
        output_legend = {key: key.upper() for (key, value) in output_legend.items()}

    print("""
- Mutation testing starting -

These are the steps:
1. A full test suite run will be made to make sure we
   can run the tests successfully and we know how long
   it takes (to detect infinite loops for example)
2. Mutants will be generated and checked

Results are stored in .mutmut-cache.
Print found mutants with `mutmut results`.

Legend for output:
{killed} Killed mutants.   The goal is for everything to end up in this bucket.
{timeout} Timeout.          Test suite took 10 times as long as the baseline so were killed.
{suspicious} Suspicious.       Tests took a long time, but not long enough to be fatal.
{survived} Survived.         This means your tests need to be expanded.
{skipped} Skipped.          Skipped.
""".format(**output_legend))
    if runner is DEFAULT_RUNNER:
        try:
            import pytest
        except ImportError:
            runner = 'python -m unittest'

    baseline_time_elapsed = time_test_suite(
        swallow_output=not swallow_output,
        test_command=runner,
        using_testmon=using_testmon,
        current_hash_of_tests=current_hash_of_tests,
    )

    if hasattr(mutmut_config, 'init'):
        mutmut_config.init()

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    # if we're running in a mode with externally whitelisted lines
    covered_lines_by_filename = None
    coverage_data = None
    if use_coverage or use_patch_file:
        covered_lines_by_filename = {}
        if use_coverage:
            coverage_data = read_coverage_data()
            check_coverage_data_filepaths(coverage_data)
        else:
            assert use_patch_file
            covered_lines_by_filename = read_patch_data(use_patch_file)

    if command != 'run':
        raise click.BadArgumentUsage("Invalid command {}".format(command))

    mutations_by_file = {}

    paths_to_exclude = paths_to_exclude or ''
    if paths_to_exclude:
        paths_to_exclude = [path.strip() for path in paths_to_exclude.replace(',', '\n').split('\n')]
        paths_to_exclude = [x for x in paths_to_exclude if x]

    config = Config(
        total=0,  # we'll fill this in later!
        swallow_output=not swallow_output,
        test_command=runner,
        covered_lines_by_filename=covered_lines_by_filename,
        coverage_data=coverage_data,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=backup,
        dict_synonyms=dict_synonyms,
        using_testmon=using_testmon,
        cache_only=cache_only,
        tests_dirs=tests_dirs,
        hash_of_tests=current_hash_of_tests,
        test_time_multiplier=test_time_multiplier,
        test_time_base=test_time_base,
        pre_mutation=pre_mutation,
        post_mutation=post_mutation,
        paths_to_mutate=paths_to_mutate,
        no_progress=no_progress
    )

    parse_run_argument(argument, config, dict_synonyms, mutations_by_file, paths_to_exclude, paths_to_mutate, tests_dirs)

    config.total = sum(len(mutations) for mutations in mutations_by_file.values())

    print()
    print('2. Checking mutants')
    progress = Progress(total=config.total, output_legend=output_legend)

    try:
        run_mutation_tests(config=config, progress=progress, mutations_by_file=mutations_by_file)
    except Exception as e:
        traceback.print_exc()
        return compute_exit_code(progress, e)
    else:
        return compute_exit_code(progress)
    finally:
        print()  # make sure we end the output with a newline
        # Close all active multiprocessing queues to avoid hanging up the main process
        close_active_queues()


def parse_run_argument(argument, config, dict_synonyms, mutations_by_file, paths_to_exclude, paths_to_mutate, tests_dirs):
    if argument is None:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs, paths_to_exclude):
                if filename.startswith('test_') or filename.endswith('__tests.py'):
                    continue
                update_line_numbers(filename)
                add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)
    else:
        try:
            int(argument)
        except ValueError:
            filename = argument
            if not os.path.exists(filename):
                raise click.BadArgumentUsage('The run command takes either an integer that is the mutation id or a path to a file to mutate')
            update_line_numbers(filename)
            add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)
            return

        filename, mutation_id = filename_and_mutation_id_from_pk(int(argument))
        update_line_numbers(filename)
        mutations_by_file[filename] = [mutation_id]


def time_test_suite(swallow_output, test_command, using_testmon, current_hash_of_tests):
    """Execute a test suite specified by ``test_command`` and record
    the time it took to execute the test suite as a floating point number

    :param swallow_output: if :obj:`True` test stdout will be not be printed
    :type swallow_output: bool

    :param test_command: command to spawn the testing subprocess
    :type test_command: str

    :param using_testmon: if :obj:`True` the test return code evaluation will
        accommodate for ``pytest-testmon``
    :type using_testmon: bool

    :return: execution time of the test suite
    :rtype: float
    """
    cached_time = cached_test_time()
    if cached_time is not None and current_hash_of_tests == cached_hash_of_tests():
        print('1. Using cached time for baseline tests, to run baseline again delete the cache file')
        return cached_time

    print('1. Running tests without mutations')
    start_time = time()

    output = []

    def feedback(line):
        if not swallow_output:
            print(line)
        print_status('Running...')
        output.append(line)

    returncode = popen_streaming_output(test_command, feedback)

    if returncode == 0 or (using_testmon and returncode == 5):
        baseline_time_elapsed = time() - start_time
    else:
        raise RuntimeError("Tests don't run cleanly without mutations. Test command was: {}\n\nOutput:\n\n{}".format(test_command, '\n'.join(output)))

    print('Done')

    set_cached_test_time(baseline_time_elapsed, current_hash_of_tests)

    return baseline_time_elapsed


if __name__ == '__main__':
    climain()
