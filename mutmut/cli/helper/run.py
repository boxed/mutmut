import os
import traceback
from io import (open, )
from os.path import exists, isdir

import click
from glob2 import glob

try:
    import mutmut_config
except ImportError:
    mutmut_config = None
from mutmut.helpers.config import Config
from mutmut.helpers.progress import Progress
from mutmut.cache import hash_of_tests
from mutmut.cli.helper.run_argument_parser import RunArgumentParser
from mutmut.cli.helper.test_suite_timer import TestSuiteTimer
from mutmut.cli.helper.utils import (split_paths, get_split_paths, copy_testmon_data, stop_creating_pyc_files,
                                     read_coverage_data, read_patch_data)
from mutmut.mutator.mutator_helper import MutatorHelper
from mutmut.tester.tester import Tester


class Run:
    null_out = open(os.devnull, 'w')
    DEFAULT_RUNNER = 'python -m pytest -x --assert=plain'

    def __init__(self, argument, paths_to_mutate, disable_mutation_types, enable_mutation_types, runner, tests_dir,
                 test_time_multiplier, test_time_base, test_processes, swallow_output, use_coverage, dict_synonyms,
                 pre_mutation, post_mutation, use_patch_file, paths_to_exclude, simple_output, no_progress, ci,
                 rerun_all):

        self.argument = argument
        self.paths_to_mutate = paths_to_mutate
        self.disable_mutation_types = disable_mutation_types
        self.enable_mutation_types = enable_mutation_types
        self.runner = runner
        self.tests_dir = tests_dir
        self.test_time_multiplier = test_time_multiplier
        self.test_time_base = test_time_base
        self.test_processes = test_processes
        self.swallow_output = swallow_output
        self.use_coverage = use_coverage
        self.dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]
        self.pre_mutation = pre_mutation
        self.post_mutation = post_mutation
        self.use_patch_file = use_patch_file
        self.paths_to_exclude = paths_to_exclude
        self.simple_output = simple_output
        self.no_progress = no_progress
        self.ci = ci
        self.rerun_all = rerun_all
        self.mutation_types_to_apply = None
        self.tests_dirs = None
        self.using_testmon = None

        self.mutator_helper = MutatorHelper()

    def set_tests_directories(self):
        tests_dirs = []
        test_paths = split_paths(self.tests_dir)

        if test_paths is None:
            raise FileNotFoundError(
                'No test folders found in current folder. Run this where there is a "tests" or "test" folder.')

        for p in test_paths:
            tests_dirs.extend(glob(p, recursive=True))

        for p in self.paths_to_mutate:
            tests_dirs.extend(get_split_paths(p, test_paths))

        self.tests_dirs = tests_dirs

    def check_bad_arguments(self):
        """
        Checks on bad arguments for the do_run function
        """

        if self.use_coverage and self.use_patch_file:
            raise click.BadArgumentUsage("You can't combine --use-coverage and --use-patch")

        if self.disable_mutation_types and self.enable_mutation_types:
            raise click.BadArgumentUsage("You can't combine --disable-mutation-types and --enable-mutation-types")

    def set_mutation_types_to_apply(self):
        """
        Get mutation types to apply and raise an error if invalid types are provided
        """

        mutation_types_to_apply = set(self.mutator_helper.mutations_by_type.keys())

        if self.enable_mutation_types:
            mutation_types_to_apply = set(mtype.strip() for mtype in self.enable_mutation_types.split(","))

        elif self.disable_mutation_types:
            mutation_types_to_apply = set(self.mutator_helper.mutations_by_type.keys()) - set(
                mtype.strip() for mtype in self.disable_mutation_types.split(","))

        self.mutation_types_to_apply = mutation_types_to_apply

    def check_invalid_types(self):
        """
        Check if the mutation types to apply are valid
        """

        invalid_types = None

        if self.enable_mutation_types:
            invalid_types = [mtype for mtype in self.mutation_types_to_apply if
                             mtype not in self.mutator_helper.mutations_by_type]
        elif self.disable_mutation_types:
            invalid_types = [mtype for mtype in self.disable_mutation_types.split(",") if
                             mtype not in self.mutator_helper.mutations_by_type]

        if invalid_types:
            raise click.BadArgumentUsage(
                f"The following are not valid mutation types: {', '.join(sorted(invalid_types))}. Valid mutation "
                f"types are: {', '.join(self.mutator_helper.mutations_by_type.keys())}")

    def check_coverage_data_filepaths(self, coverage_data):
        for filepath in coverage_data:
            if not os.path.exists(filepath):
                raise ValueError('Filepaths in .coverage not recognized, try recreating the .coverage file manually.')

    def check_coverage_file(self):
        """
        Check if the coverage file exists
        """

        if self.use_coverage and not exists('.coverage'):
            raise FileNotFoundError('No .coverage file found. You must generate a coverage file to use this feature.')

    def guess_paths_to_mutate(self) -> str:
        """Guess the path to source code to mutate"""
        this_dir = os.getcwd().split(os.sep)[-1]
        if isdir('lib'):
            return 'lib'
        elif isdir('src'):
            return 'src'
        elif isdir(this_dir):
            return this_dir
        elif isdir(this_dir.replace('-', '_')):
            return this_dir.replace('-', '_')
        elif isdir(this_dir.replace(' ', '_')):
            return this_dir.replace(' ', '_')
        elif isdir(this_dir.replace('-', '')):
            return this_dir.replace('-', '')
        elif isdir(this_dir.replace(' ', '')):
            return this_dir.replace(' ', '')
        raise FileNotFoundError(
            'Could not figure out where the code to mutate is. '
            'Please specify it on the command line using --paths-to-mutate, '
            'or by adding "paths_to_mutate=code_dir" in pyproject.toml or setup.cfg to the [mutmut] '
            'section.')

    def check_paths_to_mutate(self):
        """
        Check if the paths to mutate are valid
        """

        if self.paths_to_mutate is None:
            self.paths_to_mutate = self.guess_paths_to_mutate()

        if not isinstance(self.paths_to_mutate, (list, tuple)):
            # If the paths_to_mutate is a string, we split it by commas or colons
            self.paths_to_mutate = split_paths(self.paths_to_mutate)

        if not self.paths_to_mutate:
            raise click.BadOptionUsage('--paths-to-mutate', 'You must specify a list of paths to mutate.'
                                                            'Either as a command line argument, or by setting '
                                                            'paths_to_mutate under the section [mutmut] in setup.cfg.'
                                                            'To specify multiple paths, separate them with commas or '
                                                            'colons (i.e: --paths-to-mutate=path1/,'
                                                            'path2/path3/,path4/).')

    def get_output_legend(self):
        """
        Get the output legend based on the simple_output flag
        """

        output_legend = {"killed": "🎉", "timeout": "⏰", "suspicious": "🤔", "survived": "🙁", "skipped": "🔇", }

        if self.simple_output:
            output_legend = {key: key.upper() for (key, value) in output_legend.items()}

        return output_legend

    def print_mutation_testing_starting(self):
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
        """.format(**self.get_output_legend()))

    def check_additional_imports(self):
        """
        Check if additional imports are needed for the runner
        """

        if self.runner is self.DEFAULT_RUNNER:
            try:
                import pytest  # noqa
            except ImportError:
                self.runner = 'python -m unittest'

        if hasattr(mutmut_config, 'init'):
            mutmut_config.init()

    def check_paths_to_exclude(self):
        """
        Check if the paths to exclude are valid
        """

        self.paths_to_exclude = self.paths_to_exclude or ''
        if self.paths_to_exclude:
            self.paths_to_exclude = [path.strip() for path in self.paths_to_exclude.replace(',', '\n').split('\n')]
            self.paths_to_exclude = [x for x in self.paths_to_exclude if x]

    def get_covered_data(self):
        """
        Get the covered data based on the use_coverage and use_patch_file flags

        :return: covered lines by filename and coverage data
        """

        covered_lines_by_filename = None
        coverage_data = None

        if self.use_coverage:
            covered_lines_by_filename = {}
            coverage_data = read_coverage_data()
            self.check_coverage_data_filepaths(coverage_data)

        elif self.use_patch_file:
            assert self.use_patch_file
            covered_lines_by_filename = read_patch_data(self.use_patch_file)

        return covered_lines_by_filename, coverage_data

    def prepare_test_directories(self):
        """
        Prepare the test directories
        """

        self.check_bad_arguments()

        self.set_mutation_types_to_apply()

        self.check_invalid_types()

        self.check_coverage_file()

        self.check_paths_to_mutate()

        self.set_tests_directories()

        del self.tests_dir

    def set_using_testmon(self):
        """
        Set using testmon flag
        """
        self.using_testmon = '--testmon' in self.runner

    def setup_config(self, current_hash_of_tests):
        """
        Set up the configuration for the mutation testing

        :param current_hash_of_tests: hash of the tests
        :return: configuration for the mutation testing
        """
        testSuiteTimer = TestSuiteTimer(swallow_output=not self.swallow_output, test_command=self.runner,
                                        using_testmon=self.using_testmon, no_progress=self.no_progress, )

        baseline_time_elapsed = testSuiteTimer.time_test_suite(current_hash_of_tests)

        copy_testmon_data(self.using_testmon)

        # if we're running in a mode with externally whitelisted lines
        covered_lines_by_filename, coverage_data = self.get_covered_data()

        self.check_paths_to_exclude()

        return Config(total=0,  # we'll fill this in later!
                      swallow_output=not self.swallow_output, test_command=self.runner,
                      covered_lines_by_filename=covered_lines_by_filename, coverage_data=coverage_data,
                      baseline_time_elapsed=baseline_time_elapsed, dict_synonyms=self.dict_synonyms,
                      using_testmon=self.using_testmon, tests_dirs=self.tests_dirs, hash_of_tests=current_hash_of_tests,
                      test_time_multiplier=self.test_time_multiplier, test_time_base=self.test_time_base,
                      pre_mutation=self.pre_mutation, post_mutation=self.post_mutation,
                      paths_to_mutate=self.paths_to_mutate,
                      mutation_types_to_apply=self.mutation_types_to_apply, no_progress=self.no_progress, ci=self.ci,
                      rerun_all=self.rerun_all)

    def do_run(self):
        """
        Run the mutation testing
        """

        self.prepare_test_directories()

        current_hash_of_tests = hash_of_tests(self.tests_dirs)

        stop_creating_pyc_files()

        self.set_using_testmon()

        self.print_mutation_testing_starting()

        self.check_additional_imports()

        config = self.setup_config(current_hash_of_tests)

        run_argument_parser = RunArgumentParser(self.argument, config, self.dict_synonyms, {},
                                                self.paths_to_exclude,
                                                self.paths_to_mutate, self.tests_dirs)

        run_argument_parser.parse_run_argument()

        mutations_by_file = run_argument_parser.mutations_by_file

        config.total = sum(len(mutations) for mutations in mutations_by_file.values())

        print()
        print('2. Checking mutants')
        progress = Progress(total=config.total, output_legend=self.get_output_legend(), no_progress=self.no_progress)
        tester = Tester()

        try:
            tester.run_mutation_tests(config=config, progress=progress, test_processes=self.test_processes,
                                      mutations_by_file=mutations_by_file)
        except Exception as e:
            traceback.print_exc()
            return progress.compute_exit_code(e)
        else:
            return progress.compute_exit_code(ci=self.ci)
        finally:
            print()  # make sure we end the output with a newline
            # Close all active multiprocessing queues to avoid hanging up the main process
            tester.queue_manager.close_active_queues()
