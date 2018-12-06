#!/usr/bin/python
# -*- coding: utf-8 -*-

import argparse
import os
import sys
from logging import getLogger
from os.path import isdir, exists
from shutil import copy

from glob2 import glob

from mutmut.cache import hash_of_tests
from mutmut.cache import print_result_cache, filename_and_mutation_id_from_pk
from mutmut.mutators import mutate_file, MutationContext
from mutmut.runner import read_coverage_data, time_test_suite, \
    python_source_files, add_mutations_by_file, run_mutation_tests

__log__ = getLogger(__name__)


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
            raise Exception('Could not figure out where the code to mutate is')
    else:
        return paths_to_mutate


def do_apply(mutation_pk, dict_synonyms, backup):
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))
    context = MutationContext(
        mutate_id=mutation_id,
        filename=filename,
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )
    if context.number_of_performed_mutations == 0:
        raise Exception(
            'No mutations performed. Are you sure the index is not too big?')


class Config(object):
    def __init__(self, swallow_output, test_command, exclude_callback,
                 baseline_time_elapsed, backup, dict_synonyms, total,
                 using_testmon, cache_only, tests_dirs, hash_of_tests):
        self.swallow_output = swallow_output
        self.test_command = test_command
        self.exclude_callback = exclude_callback
        self.baseline_time_elapsed = baseline_time_elapsed
        self.backup = backup
        self.dict_synonyms = dict_synonyms
        self.total = total
        self.using_testmon = using_testmon
        self.progress = 0
        self.skipped = 0
        self.cache_only = cache_only
        self.tests_dirs = tests_dirs
        self.hash_of_tests = hash_of_tests
        self.killed_mutants = 0
        self.surviving_mutants = 0
        self.surviving_mutants_timeout = 0
        self.suspicious_mutants = 0

    def print_progress(self):
        print(
            'Mutation: {}/{}  Mutant Stats: KILLED:{:5d}  TIMEOUT:{:5d}  SUSPICIOUS:{:5d}  ALIVE:{:5d}'.format(
            self.progress, self.total, self.killed_mutants,
            self.surviving_mutants_timeout, self.suspicious_mutants,
            self.surviving_mutants))


DEFAULT_TESTS_DIR = 'tests/:test/'


def get_argparser() -> argparse.ArgumentParser:
    """get the main arguement parser for mutmut"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-coverage", action="store_true",
                        dest="use_coverage")
    parser.add_argument("--paths-to-mutate", default=".", dest="mutate_paths")
    parser.add_argument("--runner", default='python -m pytest -x',
                        help="The python test runner (and its arguments) to "
                             "invoke each mutation test run")
    parser.add_argument("--results", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--apply")
    parser.add_argument("--tests-dir", dest="tests_dir", default="tests")
    parser.add_argument("-s", action="store_true", dest="output_capture",
                        help="turn off output capture")
    parser.add_argument("--cache-only", action="store_true", dest="cache_only")
    return parser


def main(argv=sys.argv[1:]):
    """main entrypoint for mutmut"""
    parser = get_argparser()
    args = parser.parse_args(argv)
    dict_synonyms = [x.strip() for x in "".split(',')]
    if args.use_coverage and not exists('.coverage'):
        raise FileNotFoundError(
            'No .coverage file found. You must generate a coverage file to use this feature.')

    if args.results:
        print_result_cache()

    if args.apply:
        do_apply(args.apply, dict_synonyms, args.backup)
        return

    paths_to_mutate = get_or_guess_paths_to_mutate(args.mutate_paths)

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise Exception(
            'You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')

    tests_dirs = []
    for p in args.tests_dir.split(':'):
        tests_dirs.extend(glob(p, recursive=True))

    for p in paths_to_mutate:
        for pt in args.tests_dir.split(':'):
            tests_dirs.extend(glob(p + '/**/' + pt, recursive=True))

    # stop python from creating .pyc files
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

    # TODO:
    using_testmon = '--testmon' in args.runner

    print("""
- Mutation testing starting - 

These are the steps:
1. A full test suite run will be made to make sure we 
   can run the tests successfully and we know how long 
   it takes (to detect infinite loops for example)
2. Mutants will be generated and checked

Mutants are written to the cache in the .mutmut-cache 
directory. Print found mutants with `mutmut results`.
""")

    baseline_time_elapsed = time_test_suite(
        swallow_output=not args.output_capture,
        test_command=args.runner,
        using_testmon=using_testmon)

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    if not args.use_coverage:
        def _exclude(context):
            return False
    else:
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

    mutations_by_file = {}

    # TODO
    argument = None

    if argument is None:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs):
                add_mutations_by_file(mutations_by_file, filename, _exclude,
                                      dict_synonyms)
    else:
        filename, mutation_id = filename_and_mutation_id_from_pk(int(argument))
        mutations_by_file[filename] = [mutation_id]


    total = sum(len(mutations) for mutations in mutations_by_file.values())

    print("Executing mutants: {}".format(total))
    print(mutations_by_file)
    config = Config(
        swallow_output=not args.output_capture,
        test_command=args.runner,
        exclude_callback=_exclude,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=args.backup,
        dict_synonyms=dict_synonyms,
        total=total,
        using_testmon=using_testmon,
        cache_only=args.cache_only,
        tests_dirs=tests_dirs,
        hash_of_tests=hash_of_tests(tests_dirs),
    )

    # TODO: return code based?
    run_mutation_tests(config=config, mutations_by_file=mutations_by_file)


if __name__ == '__main__':
    sys.exit(main())
