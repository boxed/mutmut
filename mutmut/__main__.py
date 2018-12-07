#!/usr/bin/python
# -*- coding: utf-8 -*-

"""main entrypoint for mutmut"""

import argparse
import logging
import os
import sys
from logging import getLogger
from os.path import exists
from shutil import copy

from mutmut.cache import hash_of_tests
from mutmut.file_collection import guess_paths_to_mutate, read_coverage_data, \
    get_python_source_files, get_tests_dirs
from mutmut.runner import time_test_suite, \
    add_mutations_by_file, run_mutation_tests, Config

__log__ = getLogger(__name__)

LOG_LEVEL_STRINGS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]

START_MESSAGE = """
=============== Mutation Testing Starting ==============

These are the steps:
1. A full test suite run will be made to make sure we 
   can run the tests successfully and we know how long 
   it takes (to detect infinite loops for example)
2. Mutants will be generated and checked

Mutants are written to the cache in the .mutmut-cache 

========================================================"""


def log_level(log_level_string: str):
    """Argparse type function for determining the specified logging level"""
    if log_level_string not in LOG_LEVEL_STRINGS:
        raise argparse.ArgumentTypeError(
            "invalid choice: {} (choose from {})".format(
                log_level_string,
                LOG_LEVEL_STRINGS
            )
        )
    return getattr(logging, log_level_string, logging.INFO)


def get_argparser() -> argparse.ArgumentParser:
    """get the main argument parser for mutmut"""
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("file_or_dir", nargs="+",
                        help="path to the source files to mutate test")
    parser.add_argument("--use-coverage", action="store_true",
                        dest="use_coverage",
                        help="only mutate code that is covered by tests note "
                             "this requires a ``.coverage`` file to exist "
                             "within the current working directory")
    parser.add_argument("--runner", default='pytest',
                        help="The python test runner (and its arguments) to "
                             "invoke each mutation test run ")
    parser.add_argument("--tests", dest="tests_dir", default="tests",
                        help="path to the testing files to challenge with"
                             "mutations")
    parser.add_argument("-s", action="store_true", dest="output_capture",
                        help="turn off output capture")

    return parser


def main(argv=sys.argv[1:]):
    """main entrypoint for mutmut"""
    # stop python from creating .pyc files
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

    parser = get_argparser()
    args = parser.parse_args(argv)

    if args.use_coverage and not exists('.coverage'):
        raise FileNotFoundError(
            'No .coverage file found. You must generate a coverage '
            'file to use this feature.'
        )

    if args.file_or_dir:
        paths_to_mutate = args.file_or_dir
    else:
        paths_to_mutate = [guess_paths_to_mutate()]

    if not paths_to_mutate:
        raise FileNotFoundError('You must specify a list of paths to mutate. '
                                'Either as a command line argument, or by '
                                'setting paths_to_mutate under the section')

    tests_dirs = get_tests_dirs(args.tests_dir, paths_to_mutate)

    print(START_MESSAGE)
    print("Using test runner: {}".format(args.runner))
    print("Captured the following source files:")
    for mutate_path in paths_to_mutate:
        print(mutate_path)
    print("Captured the following test files:")
    for test_dir in tests_dirs:
        print(test_dir)

    using_testmon = '--testmon' in args.runner
    baseline_time_elapsed = time_test_suite(
        swallow_output=not args.output_capture,
        test_command=args.runner,
        using_testmon=using_testmon)

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')
        print("Using testmon: '{}'->'{}'".format('.testmondata',
                                                 '.testmondata-initial'))

    if not args.use_coverage:
        def _exclude(context):
            return False
    else:
        covered_lines_by_filename = {}
        coverage_data = read_coverage_data()
        print("Using coverage data at: '.coverage'")

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

    print("Captured the following source files and mutations")
    print("{}{:<15}".format("file", "No Mutations"))
    mutations_by_file = {}
    for path in paths_to_mutate:
        for filename in get_python_source_files(path, tests_dirs):
            add_mutations_by_file(mutations_by_file, filename, _exclude)
            print("{:<}{:>15}".format(filename,
                                      len(mutations_by_file[filename])))

    total = sum(len(mutations) for mutations in mutations_by_file.values())
    print("Collected {} mutations from {} file".format(total,
                                                       len(paths_to_mutate)))
    print()
    return run_mutation_tests(
        config=Config(
            swallow_output=not args.output_capture,
            test_command=args.runner,
            exclude_callback=_exclude,
            baseline_time_elapsed=baseline_time_elapsed,
            total=total,
            using_testmon=using_testmon,
            tests_dirs=tests_dirs,
            hash_of_tests=hash_of_tests(tests_dirs),
        ),
        mutations_by_file=mutations_by_file
    )


if __name__ == '__main__':
    sys.exit(main())
