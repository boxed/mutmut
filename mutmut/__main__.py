#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Main entrypoint definitions for mutmut"""

import argparse
import os
import sys
from os.path import exists
from shutil import copy

from mutmut.cache import hash_of_tests
from mutmut.file_collection import guess_paths_to_mutate, read_coverage_data, \
    get_python_source_files, get_tests_dirs
from mutmut.runner import time_test_suite, \
    add_mutations_by_file, run_mutation_tests, Config


def get_argparser():
    """Get the main argument parser for mutmut

    :return: the main argument parser for mutmut
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("file_or_dir", nargs="+",
                        help="path to the source files to mutate test")
    parser.add_argument("--use-coverage", dest="use_coverage",
                        help="only mutate code that is covered by tests note "
                             "this requires a ``.coverage`` file path to be "
                             "given")
    parser.add_argument("--runner", default='python -m pytest -x',
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

    if args.use_coverage and not exists(args.use_coverage):
        raise FileNotFoundError(
            'Specified coverage file: {} not found. You must generate a '
            'coverage file to use this feature.'.format(args.use_coverage)
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

    print("{:=^79}".format(" Starting Mutation Tests "))
    print("Using test runner: {}".format(args.runner))

    using_testmon = '--testmon' in args.runner
    baseline_time_elapsed = time_test_suite(
        swallow_output=not args.output_capture,
        test_command=args.runner,
        using_testmon=using_testmon)
    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    if args.use_coverage:
        covered_lines_by_filename = {}
        coverage_data = read_coverage_data(args.use_coverage)
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
    else:
        def _exclude(context):
            return False

    mutations_by_file = {}

    for path in paths_to_mutate:
        for filename in get_python_source_files(path, tests_dirs):
            add_mutations_by_file(mutations_by_file, filename, _exclude)

    total = sum(len(mutations) for mutations in mutations_by_file.values())
    print("Collected {} mutations from {} file".format(
        total, len(paths_to_mutate)))
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
