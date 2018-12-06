#!/usr/bin/python
# -*- coding: utf-8 -*-
import datetime
import os
import subprocess
from os.path import isdir
from shutil import move, copy

from mutmut.cache import get_cached_mutation_status, update_mutant_status, \
    set_cached_test_time, register_mutants, cached_test_time, get_mutation_diff
from mutmut.mutators import MutationContext, BAD_SURVIVED, BAD_TIMEOUT, \
    OK_KILLED, OK_SUSPICIOUS, list_mutations, UNTESTED, mutate_file


def popen_streaming_output(cmd, callback, timeout=None):
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    while p.returncode is None:
        try:
            output, errors = p.communicate(timeout=timeout)
            if output.endswith("\n"):
                # -1 to remove the newline at the end
                output = output[:-1]
            line = output
            callback(line)
        except OSError:
            # This seems to happen on some platforms, including TravisCI. It seems like
            # it's ok to just let this pass here, you just won't get as nice feedback.
            pass
        except subprocess.TimeoutExpired:
            p.kill()
            raise

    return p.returncode


def tests_pass(config):
    """

    :param config:
    :type config: Config
    :return:
    """
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    def feedback(line):
        if not config.swallow_output:
            print(line)

    returncode = popen_streaming_output(config.test_command, feedback,
                                        timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def run_uncached_mutation(config, filename, mutation_id) -> str:
    """Run a mutation test that is currently not existing within the cache
    or reported to be ``UNTESTED``

    :param config:
    :type config: Config

    :param filename:
    :type filename: str

    :param mutation_id:
    :type mutation_id: tuple[str, int]

    :return: the status of running the mutation test
    :rtype: str
    """
    context = MutationContext(
        mutate_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        config=config,
    )

    try:
        number_of_mutations_performed = mutate_file(
            backup=True,
            context=context
        )
        assert number_of_mutations_performed
        start = datetime.datetime.now()
        try:
            survived = tests_pass(config)
        except TimeoutError:
            context.config.surviving_mutants_timeout += 1
            return BAD_TIMEOUT

        time_elapsed = datetime.datetime.now() - start
        if time_elapsed.total_seconds() > config.baseline_time_elapsed * 2:
            config.suspicious_mutants += 1
            return OK_SUSPICIOUS

        if survived:
            context.config.surviving_mutants += 1
            return BAD_SURVIVED
        else:
            context.config.killed_mutants += 1
            return OK_KILLED
    finally:
        move(filename + '.bak', filename)


def get_mutation_test_status(config, filename, mutation_id) -> str:
    """Obtain a mutation test's status by either obtaining the cached result
    or by running the mutation test.

    :param config:
    :type config: Config

    :param filename:
    :type filename: str

    :param mutation_id:
    :type mutation_id: tuple[str, int]

    :return:
    :rtype: str
    """
    status = get_cached_mutation_status(filename, mutation_id,
                                        config.hash_of_tests)
    if status == BAD_SURVIVED:
        config.surviving_mutants += 1
    elif status == BAD_TIMEOUT:
        config.surviving_mutants_timeout += 1
    elif status == OK_KILLED:
        config.killed_mutants += 1
    elif status == OK_SUSPICIOUS:
        config.suspicious_mutants += 1
    elif status == UNTESTED:
        status = run_uncached_mutation(config, filename, mutation_id)
    else:
        raise ValueError("unknown status obtained by "
                         "get_cached_mutation_status: {}".format(status))

    # at this point we are done the mutation test run
    config.print_progress()

    if not (status == OK_KILLED or status == OK_SUSPICIOUS):
        mutation_diff = get_mutation_diff(filename, mutation_id)
        print(
            "Mutation test failure! Status: {} Mutation: {} source: {}".format(
                status, config.progress + 1, filename))
        print(*mutation_diff)

    return status


def run_mutation_tests_for_file(config, file_to_mutate, mutations):
    """

    :param config:
    :type config: Config

    :param file_to_mutate:
    :type file_to_mutate: str

    :param mutations:
    :type mutations: list[

    :return:
    """
    for mutation_id in mutations:
        status = get_mutation_test_status(config, file_to_mutate, mutation_id)
        update_mutant_status(file_to_mutate, mutation_id, status,
                             config.hash_of_tests)
        config.progress += 1


def fail_on_cache_only(config):
    """

    :param config:
    :type config: Config
    :return:
    """
    if config.cache_only:
        print('\rFAILED: changes detected in cache only mode')
        exit(2)


def run_mutation_tests(config, mutations_by_file):
    """
    :type config: Config
    :type mutations_by_file: dict[str, list[tuple[str, int]]]
    """
    for file_to_mutate, mutations in mutations_by_file.items():
        run_mutation_tests_for_file(config, file_to_mutate, mutations)


def read_coverage_data(use_coverage):
    """

    :param use_coverage:
    :type use_coverage: bool
    :return:
    """
    if use_coverage:
        print('Using coverage data from .coverage file')
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        import coverage
        coverage_data = coverage.CoverageData()
        coverage_data.read_file('.coverage')
        return coverage_data
    else:
        return None


def time_test_suite(swallow_output, test_command, using_testmon):
    """Obtain the run-time of a test suite on a non mutated code source.
    This is used to obtain an approximate run-time for setting the mutation
    test run timeout value.

    :param swallow_output:
    :type swallow_output: bool

    :param test_command:

    :param using_testmon:
    :type using_testmon: bool
    :return:
    """
    cached_time = cached_test_time()
    if cached_time is not None:
        print('1. Using cached time for baseline tests, to run baseline '
              'again delete the cache file')
        return cached_time

    print('1. Running tests without mutations')
    start_time = datetime.datetime.now()

    output = []

    def feedback(line):
        if not swallow_output:
            print(line)
        print('Running...')
        output.append(line)

    returncode = popen_streaming_output(test_command, feedback)

    if returncode == 0 or (using_testmon and returncode == 5):
        baseline_time_elapsed = (
                    datetime.datetime.now() - start_time).total_seconds()
    else:
        raise Exception(
            "Tests don't run cleanly without mutations. "
            "Test command was: {}\n\nOutput:\n\n{}".format(test_command,
                                                           output)
        )

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, exclude):
    context = MutationContext(
        source=open(filename).read(),
        filename=filename,
        exclude=exclude,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        register_mutants(mutations_by_file)
    except Exception:
        print('Failed while creating mutations for %s, for line "%s"' % (
            context.filename, context.current_source_line))
        raise


def coverage_exclude_callback(context, use_coverage, coverage_data):
    """

    :param context:
    :type context: MutationContext

    :param use_coverage:
    :type use_coverage: bool

    :param coverage_data: TODO
    :return:
    :rtype: bool
    """
    if use_coverage:
        measured_lines = coverage_data.lines(os.path.abspath(context.filename))
        if measured_lines is None:
            return True
        current_line = context.current_line_index + 1
        if current_line not in measured_lines:
            return True
    return False


def python_source_files(path, tests_dirs):
    """

    :param path:
    :type path: str

    :param tests_dirs:
    :type tests_dirs: list[str]

    :return:
    :rtype:
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


class Config(object):
    def __init__(self, swallow_output, test_command, exclude_callback,
                 baseline_time_elapsed, backup, total,
                 using_testmon, cache_only, tests_dirs, hash_of_tests):
        self.swallow_output = swallow_output
        self.test_command = test_command
        self.exclude_callback = exclude_callback
        self.baseline_time_elapsed = baseline_time_elapsed
        self.backup = backup
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
            'Mutation: {:5d}/{}  Mutant Stats: KILLED:{:5d}  TIMEOUT:{:5d}  SUSPICIOUS:{:5d}  ALIVE:{:5d}'.format(
                self.progress + 1, self.total, self.killed_mutants,
                self.surviving_mutants_timeout, self.suspicious_mutants,
                self.surviving_mutants))
