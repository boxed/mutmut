#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Mutation test management and execution"""

import subprocess
import time
import traceback
from difflib import unified_diff
from shutil import move, copy

from mutmut.cache import get_cached_mutation_status, update_mutant_status, \
    set_cached_test_time, register_mutants, get_cached_test_time, \
    UNTESTED, OK_SUSPICIOUS, OK_KILLED, BAD_SURVIVED, \
    BAD_TIMEOUT, get_differ
from mutmut.mutators import MutationContext, list_mutations, mutate_file


def compute_return_code(config, exception=None):
    """Compute an error code similar to how pylint does. (using bit OR)

    The following output status codes are available for mutmut:
     * 0 if all mutants were killed (OK_KILLED)
     * 1 if a fatal error occurred
     * 2 if one or more mutants survived (BAD_SURVIVED)
     * 4 if one or more mutants timed out (BAD_TIMEOUT)
     * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)
     status codes 1 to 8 will be bit-ORed so you can know which different
     categories has been issued by analysing the mutmut output status code

    :param exception:
    :type exception: Exception
    :param config:
    :type config: Config

    :return: a integer noting the return status of the mutation tests.
    :rtype: int
    """
    code = 0
    if exception is not None:
        code = code | 1
    if config.surviving_mutants > 0:
        code = code | 2
    if config.surviving_mutants_timeout > 0:
        code = code | 4
    if config.suspicious_mutants > 0:
        code = code | 8
    return code


def popen_streaming_output(cmd, callback, timeout=None):
    """Open a subprocess and stream its output without hard-blocking.

    :param cmd: the command to execute within the subprocess
    :type cmd: str

    :param callback: function to execute with the subprocess stdout output
    :param timeout: the timeout time for the processes' ``communication``
        call to complete
    :type timeout: float

    :raises subprocess.TimeoutExpired: if the exciting subprocesses'
        ``communication`` call times out

    :return: the return code of the executed subprocess
    :rtype: int
    """
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
            # This seems to happen on some platforms, including TravisCI.
            # It seems like it's ok to just let this pass here, you just
            # won't get as nice feedback.
            pass
        except subprocess.TimeoutExpired:
            p.kill()
            raise

    return p.returncode


def tests_pass(config):
    """Run the test command and obtain a boolean noting if the test
    suite has passed

    :param config:
    :type config: Config

    :return: a boolean noting if the test suite has passed
    :rtype: bool
    """
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    def feedback(line):
        if not config.swallow_output:
            print(line)

    returncode = popen_streaming_output(config.test_command, feedback,
                                        timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def run_untested_mutation(config, filename, mutation_id) -> str:
    """Run a mutation test that is currently reported to be ``UNTESTED``.
    Likely this mutation is brand new, recently updated, or  not existing
    within the cache.

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
        start = time.time()
        try:
            survived = tests_pass(config)
        except subprocess.TimeoutExpired:
            context.config.surviving_mutants_timeout += 1
            return BAD_TIMEOUT

        time_elapsed = time.time() - start
        if time_elapsed > config.baseline_time_elapsed * 2:
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


def get_mutation_original_pair(source, mutated_source):
    mutant = set(mutated_source.splitlines(keepends=True))
    normie = set(source.splitlines(keepends=True))
    mutation = list(mutant - normie)
    assert 1 == len(mutation)
    original = list(normie - mutant)
    assert 1 == len(original)
    return original[0].strip(), mutation[0].strip()


def get_mutation_test_status(config, filename, mutation_id) -> str:
    """Obtain a mutation test's status by either obtaining the cached result
    or by running the mutation test.

    :param config:
    :type config: Config

    :param filename: the source file that was mutated within this test
    :type filename: str

    :param mutation_id:
    :type mutation_id: tuple[str, int]

    :return: the status of the executed mutation test
    :rtype: str
    """
    source, mutated_source = get_differ(filename, mutation_id)
    original, mutation = get_mutation_original_pair(source, mutated_source)
    print("{}['{}'->'{}'] ".format(filename, original, mutation), end='')
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
        status = run_untested_mutation(config, filename, mutation_id)
    else:
        raise ValueError("Unknown mutation test status: {}".format(status))

    # at this point we are done the mutation test run
    config.progress += 1
    print(status)

    if not (status == OK_KILLED or status == OK_SUSPICIOUS):
        print(*unified_diff(source.splitlines(keepends=True),
                            mutated_source.splitlines(keepends=True),
                            fromfile=filename, tofile=filename))

    return status


def run_mutation_tests(config, mutations_by_file, catch_exception=True):
    """Run a series of mutations tests with the given config and mutations
    per file.

    :param config:
    :type config: Config

    :param mutations_by_file:
    :type mutations_by_file: dict[str, list[tuple[str, int]]]

    :param catch_exception: boolean indicating whether mutmut should catch
        exceptions during mutation testing. This should be normally left on.
    :type catch_exception: bool

    :return: a integer noting the return status of the mutation tests.
    :rtype: int
    """
    start = time.time()
    try:
        for file_to_mutate, mutations in mutations_by_file.items():
            run_mutation_tests_for_file(config, file_to_mutate, mutations)
    except Exception as exception:
        print("Exception during mutation tests!")
        traceback.print_exc()
        if not catch_exception:
            raise exception
        return compute_return_code(config, exception)
    else:
        print("All mutation tests executed successfully")
        return compute_return_code(config)
    finally:
        print("{:=^79}".format(
            ' KILLED:{} SUSPICIOUS:{} TIMEOUT:{} ALIVE:{} '.format(
                config.killed_mutants,
                config.suspicious_mutants,
                config.surviving_mutants_timeout,
                config.surviving_mutants)
        )
        )
        print("Executed {}/{} Mutations in {:.3f} seconds".format(
            config.progress, config.total, time.time() - start))

        if config.surviving_mutants + config.surviving_mutants_timeout > 0:
            print("WARNING: Surviving mutants detected you should "
                  "improve your tests")
        else:
            print("No surviving mutants detected you should **still**"
                  "improve your tests")


def run_mutation_tests_for_file(config, file_to_mutate, mutations):
    """

    :param config:
    :type config: Config

    :param file_to_mutate:
    :type file_to_mutate: str

    :param mutations:
    :type mutations:

    :return:
    """
    for mutation_id in mutations:
        status = get_mutation_test_status(config, file_to_mutate, mutation_id)
        update_mutant_status(file_to_mutate, mutation_id, status,
                             config.hash_of_tests)


def time_test_suite(swallow_output, test_command, using_testmon) -> float:
    """Obtain the run-time of a test suite on a non mutated code source.
    This is used to obtain an approximate run-time for setting the mutation
    test run timeout value.

    :param swallow_output:
    :type swallow_output: bool

    :param test_command:
    :type test_command: str

    :param using_testmon:
    :type using_testmon: bool

    :return:
    :rtype: float
    """
    cached_time = get_cached_test_time()
    if cached_time is not None:
        print(
            "Using cached baseline tests execution time: {}\n"
            "Note: to reset this value delete the '.mutmut-cache'".format(
                cached_time)
        )
        return cached_time

    print('Running tests without mutations: cmd: {}'.format(test_command))
    start_time = time.time()

    output = []

    def feedback(line):
        if not swallow_output:
            print(line)
        output.append(line)

    returncode = popen_streaming_output(test_command, feedback)

    if returncode == 0 or (using_testmon and returncode == 5):
        baseline_time_elapsed = time.time() - start_time
        print("Obtained test execution time without mutations: {}".format(
            baseline_time_elapsed))
    else:
        raise RuntimeError(
            "Tests don't run cleanly without mutations. "
            "Test command was: {}\nOutput:\n{}".format(
                test_command, "".join(output)
            )
        )

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, exclude):
    """

    :param mutations_by_file:
    :type mutations_by_file: dict[str, list[tuple[str, int]]]

    :param filename: the file to create mutations in
    :type filename: str

    :param exclude:
    """
    context = MutationContext(
        source=open(filename).read(),
        filename=filename,
        exclude=exclude,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        register_mutants(mutations_by_file)
    except Exception:
        print(
            "Failed creating mutations for file: {} on line: {}".format(
                context.filename, context.current_source_line
            )
        )
        raise


class Config(object):
    """Container for all the needed configuration for a mutation test run"""

    def __init__(self, swallow_output, test_command, exclude_callback,
                 baseline_time_elapsed, total,
                 using_testmon, tests_dirs, hash_of_tests):
        self.swallow_output = swallow_output
        self.test_command = test_command
        self.exclude_callback = exclude_callback
        self.baseline_time_elapsed = baseline_time_elapsed
        self.total = total
        self.using_testmon = using_testmon
        self.progress = 0
        self.skipped = 0
        self.tests_dirs = tests_dirs
        self.hash_of_tests = hash_of_tests
        self.killed_mutants = 0
        self.surviving_mutants = 0
        self.surviving_mutants_timeout = 0
        self.suspicious_mutants = 0

