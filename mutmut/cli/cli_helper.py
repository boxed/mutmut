#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import traceback
from io import (
    open,
)
from os.path import exists
from pathlib import Path
from shutil import copy
from time import time
from typing import List

import click
from glob2 import glob

from mutmut import (
    mutate_file,
    Context,
    mutmut_config,
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
    cached_hash_of_tests,
)
from mutmut.cache import hash_of_tests, \
    filename_and_mutation_id_from_pk, cached_test_time, set_cached_test_time, \
    update_line_numbers
from mutmut.mutator import mutations_by_type

DEFAULT_RUNNER = 'python -m pytest -x --assert=plain'
null_out = open(os.devnull, 'w')


def do_apply(mutation_pk: str, dict_synonyms: List[str], backup: bool):
    """Apply a specified mutant to the source code

    :param mutation_pk: mutmut cache primary key of the mutant to apply
    :param dict_synonyms: list of synonym keywords for a python dictionary
    :param backup: if :obj:`True` create a backup of the source file
        before applying the mutation
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


"""
CodeScene analysis:
    This function is prioritized to be refactored because of :
        - Complex method: cyclomatic complexity equal to 47, with threshold equal to 9
        - Excess number of function arguments: 19 arguments, with threshold equal to 4
        - Bumpy Road Ahead: 4 blocks with nested conditional logic, any nesting of 2 or deeper is considered, 
            with threshold equal to one single nested block per function [fixed]
"""


def do_run(
        argument,
        paths_to_mutate,
        disable_mutation_types,
        enable_mutation_types,
        runner,
        tests_dir,
        test_time_multiplier,
        test_time_base,
        swallow_output,
        use_coverage,
        dict_synonyms,
        pre_mutation,
        post_mutation,
        use_patch_file,
        paths_to_exclude,
        simple_output,
        no_progress,
        ci,
        rerun_all,
) -> int:
    """return exit code, after performing a mutation test run.

    :return: the exit code from executing the mutation tests for run command
    """

    # Check bad arguments
    check_bad_arguments(use_coverage, use_patch_file, disable_mutation_types, enable_mutation_types)

    # Get mutation types to apply
    mutation_types_to_apply = get_mutation_types_to_apply(enable_mutation_types, disable_mutation_types)

    # Check invalid types
    check_invalid_types(mutation_types_to_apply, enable_mutation_types, disable_mutation_types)

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if use_coverage and not exists('.coverage'):
        raise FileNotFoundError('No .coverage file found. You must generate a coverage file to use this feature.')

    # Check paths to mutate
    paths_to_mutate = check_paths_to_mutate(paths_to_mutate)

    tests_dirs = get_tests_directories(tests_dir, paths_to_mutate)

    del tests_dir
    current_hash_of_tests = hash_of_tests(tests_dirs)

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    using_testmon = '--testmon' in runner

    # get output legend
    output_legend = get_output_legend(simple_output)

    # Print mutation testing starting
    print_mutation_testing_starting(output_legend)

    # Check additional imports for the runner and mutmut_config
    runner = check_additional_imports(runner)

    testSuiteTimer = TestSuiteTimer(
        swallow_output=not swallow_output,
        test_command=runner,
        using_testmon=using_testmon,
        no_progress=no_progress,
    )

    baseline_time_elapsed = testSuiteTimer.time_test_suite(current_hash_of_tests)

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    # if we're running in a mode with externally whitelisted lines
    covered_lines_by_filename = None
    coverage_data = None

    if use_coverage:
        covered_lines_by_filename = {}
        coverage_data = read_coverage_data()
        check_coverage_data_filepaths(coverage_data)

    elif use_patch_file:
        assert use_patch_file
        covered_lines_by_filename = read_patch_data(use_patch_file)

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
        dict_synonyms=dict_synonyms,
        using_testmon=using_testmon,
        tests_dirs=tests_dirs,
        hash_of_tests=current_hash_of_tests,
        test_time_multiplier=test_time_multiplier,
        test_time_base=test_time_base,
        pre_mutation=pre_mutation,
        post_mutation=post_mutation,
        paths_to_mutate=paths_to_mutate,
        mutation_types_to_apply=mutation_types_to_apply,
        no_progress=no_progress,
        ci=ci,
        rerun_all=rerun_all
    )

    parse_run_argument(argument, config, dict_synonyms, mutations_by_file, paths_to_exclude, paths_to_mutate,
                       tests_dirs)

    config.total = sum(len(mutations) for mutations in mutations_by_file.values())

    print()
    print('2. Checking mutants')
    progress = Progress(total=config.total, output_legend=output_legend, no_progress=no_progress)

    try:
        run_mutation_tests(config=config, progress=progress, mutations_by_file=mutations_by_file)
    except Exception as e:
        traceback.print_exc()
        return compute_exit_code(progress, e)
    else:
        return compute_exit_code(progress, ci=ci)
    finally:
        print()  # make sure we end the output with a newline
        # Close all active multiprocessing queues to avoid hanging up the main process
        close_active_queues()


def split_paths(paths):
    # This method is used to split paths that are separated by commas or colons
    for sep in [',', ':']:
        separated = list(filter(lambda p: Path(p).exists(), paths.split(sep)))
        if separated:
            return separated
    return None


def get_tests_directories(tests_dir, paths_to_mutate):
    tests_dirs = []
    test_paths = split_paths(tests_dir)

    if test_paths is None:
        raise FileNotFoundError(
            'No test folders found in current folder. Run this where there is a "tests" or "test" folder.'
        )

    for p in test_paths:
        tests_dirs.extend(glob(p, recursive=True))

    for p in paths_to_mutate:
        tests_dirs.extend(get_split_paths(p, test_paths))

    return tests_dirs


def get_split_paths(p, test_paths):
    split = []

    for pt in test_paths:
        split.extend(glob(p + '/**/' + pt, recursive=True))

    return split


def check_bad_arguments(use_coverage, use_patch_file, disable_mutation_types, enable_mutation_types):
    """
    Checks on bad arguments for the do_run function

    :param use_coverage: whether to use coverage
    :param use_patch_file: whether to use patch file
    :param disable_mutation_types: mutation types to disable
    :param enable_mutation_types: mutation types to enable
    """

    if use_coverage and use_patch_file:
        raise click.BadArgumentUsage("You can't combine --use-coverage and --use-patch")

    if disable_mutation_types and enable_mutation_types:
        raise click.BadArgumentUsage("You can't combine --disable-mutation-types and --enable-mutation-types")


def get_mutation_types_to_apply(enable_mutation_types, disable_mutation_types):
    """
    Get mutation types to apply and raise an error if invalid types are provided

    :param enable_mutation_types: mutation types to enable
    :param disable_mutation_types: mutation types to disable
    :return: mutation types to apply
    """

    mutation_types_to_apply = set(mutations_by_type.keys())

    if enable_mutation_types:
        mutation_types_to_apply = set(mtype.strip() for mtype in enable_mutation_types.split(","))

    elif disable_mutation_types:
        mutation_types_to_apply = set(mutations_by_type.keys()) - set(
            mtype.strip() for mtype in disable_mutation_types.split(","))

    return mutation_types_to_apply


def check_invalid_types(mutation_types_to_apply, enable_mutation_types, disable_mutation_types):
    """
    Check if the mutation types to apply are valid

    :param mutation_types_to_apply: mutation types to apply
    :param enable_mutation_types: mutation types to enable
    :param disable_mutation_types: mutation types to disable
    """

    invalid_types = None

    if enable_mutation_types:
        invalid_types = [mtype for mtype in mutation_types_to_apply if mtype not in mutations_by_type]
    elif disable_mutation_types:
        invalid_types = [mtype for mtype in disable_mutation_types.split(",") if mtype not in mutations_by_type]

    if invalid_types:
        raise click.BadArgumentUsage(
            f"The following are not valid mutation types: {', '.join(sorted(invalid_types))}. Valid mutation types are: {', '.join(mutations_by_type.keys())}")


def check_paths_to_mutate(paths_to_mutate):
    """
    Check if the paths to mutate are valid

    :param paths_to_mutate: paths to mutate
    """

    if paths_to_mutate is None:
        paths_to_mutate = guess_paths_to_mutate()

    if not isinstance(paths_to_mutate, (list, tuple)):
        # If the paths_to_mutate is a string, we split it by commas or colons
        paths_to_mutate = split_paths(paths_to_mutate)

    if not paths_to_mutate:
        raise click.BadOptionUsage(
            '--paths-to-mutate',
            'You must specify a list of paths to mutate.'
            'Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg.'
            'To specify multiple paths, separate them with commas or colons (i.e: --paths-to-mutate=path1/,'
            'path2/path3/,path4/).'
        )

    return paths_to_mutate


def get_output_legend(simple_output):
    """
    Get the output legend based on the simple_output flag

    :param simple_output: flag to determine if the output should be simple
    :return: output legend
    """

    output_legend = {
        "killed": "🎉",
        "timeout": "⏰",
        "suspicious": "🤔",
        "survived": "🙁",
        "skipped": "🔇",
    }

    if simple_output:
        output_legend = {key: key.upper() for (key, value) in output_legend.items()}

    return output_legend


def print_mutation_testing_starting(output_legend):
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


def check_additional_imports(runner):
    """
    Check if additional imports are needed for the runner

    :param runner: runner to check
    :return: the new or default runner
    """
    if runner is DEFAULT_RUNNER:
        try:
            import pytest  # noqa
        except ImportError:
            runner = 'python -m unittest'

    if hasattr(mutmut_config, 'init'):
        mutmut_config.init()

    return runner


"""
CodeScene analysis:
    This function is recommended to be refactored because of:
        - Complex method: cyclomatic complexity equal to 10, with threshold equal to 9
        - Excess number of function arguments: 7 arguments, with threshold equal to 4
        - Bumpy Road Ahead: 2 blocks with nested conditional logic, any nesting of 2 or deeper is considered, 
            with threshold equal to one single nested block per function
        - Deep, Nested Complexity: a nested complexity depth of 4, with threshold equal to 4
"""


def parse_run_argument(argument, config, dict_synonyms, mutations_by_file, paths_to_exclude, paths_to_mutate,
                       tests_dirs):
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
                raise click.BadArgumentUsage(
                    'The run command takes either an integer that is the mutation id or a path to a file to mutate')
            update_line_numbers(filename)
            add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)
            return

        filename, mutation_id = filename_and_mutation_id_from_pk(int(argument))
        update_line_numbers(filename)
        mutations_by_file[filename] = [mutation_id]


"""
CodeScene analysis:
    This function is prioritized to be refactored because of :
        - Complex method: cyclomatic complexity equal to 10, with threshold equal to 9 [fixed]
        - Excess number of function arguments: 5 arguments, with threshold equal to 4
        - Complex conditional: 1 complex conditional with 2 branches, with threshold equal to 2 
            [fixed -> moved to calculate_baseline_time]
"""


class TestSuiteTimer:

    def __init__(self, swallow_output: bool, test_command: str, using_testmon: bool, no_progress: bool):

        self.swallow_output = swallow_output
        self.test_command = test_command
        self.using_testmon = using_testmon
        self.no_progress = no_progress

    def run_tests_without_mutations(self):
        """Execute a test suite specified by ``test_command`` and record
        the time it took to execute the test suite as a floating point number

        :return: execution time of the test suite
        """

        output = []

        def feedback(line):
            if not self.swallow_output:
                print(line)
            if not self.no_progress:
                print_status('Running...')
            output.append(line)

        return_code = popen_streaming_output(self.test_command, feedback)

        return return_code, output

    def check_test_run_cleanliness(self, return_code: int) -> bool:
        """
        Check if the test suite ran cleanly without any errors

        :param return_code: return code of the test suite
        :return: True if the test suite ran cleanly without any errors, False otherwise
        """

        return return_code == 0 or (self.using_testmon and return_code == 5)

    def calculate_baseline_time(self, return_code: int, start_time: float, output: list[str]):
        """
        Calculate the baseline time elapsed for the test suite

        :param return_code: return code of the test suite
        :param start_time: start time of the test suite
        :param output: output of the test suite
        :return baseline_time_elapsed: execution time of the test suite
        """

        if self.check_test_run_cleanliness(return_code):
            baseline_time_elapsed = time() - start_time
        else:
            raise RuntimeError(
                "Tests don't run cleanly without mutations. Test command was: {}\n\nOutput:\n\n{}".format(
                    self.test_command,
                    '\n'.join(
                        output)))

        return baseline_time_elapsed

    def time_test_suite(self, current_hash_of_tests) -> float:
        """Execute a test suite specified by ``test_command`` and record
        the time it took to execute the test suite as a floating point number

        :param current_hash_of_tests: hash of the test suite
        :return: execution time of the test suite
        """

        cached_time = cached_test_time()
        if cached_time is not None and current_hash_of_tests == cached_hash_of_tests():
            print('1. Using cached time for baseline tests, to run baseline again delete the cache file')
            return cached_time

        print('1. Running tests without mutations')
        start_time = time()
        return_code, output = self.run_tests_without_mutations()

        baseline_time_elapsed = self.calculate_baseline_time(return_code, start_time, output)
        print('Done')

        set_cached_test_time(baseline_time_elapsed, current_hash_of_tests)

        return baseline_time_elapsed
