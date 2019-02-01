# -*- coding: utf-8 -*-

import itertools
import os
import shlex
import subprocess
import sys
from shutil import copy
from threading import Timer
from time import time

from mutmut.cache import cached_test_time, set_cached_test_time
from mutmut.mutator import UNTESTED, \
    OK_KILLED, OK_SUSPICIOUS, BAD_TIMEOUT, BAD_SURVIVED
from mutmut.utils import print, TimeoutError

spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')


def status_printer():
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]

    def p(s):
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        sys.stdout.write(output)
        sys.stdout.flush()
        last_len[0] = len_s

    return p


print_status = status_printer()


def popen_streaming_output(cmd, callback, timeout=None):
    """Open a subprocess and stream its output without hard-blocking.

    :param cmd: the command to execute within the subprocess
    :type cmd: str

    :param callback: function that intakes the subprocess' stdout line by line.
        It is called for each line received from the subprocess' stdout stream.
    :type callback: Callable[[Context], bool]

    :param timeout: the timeout time of the subprocess
    :type timeout: float

    :raises TimeoutError: if the subprocess' execution time exceeds
        the timeout time

    :return: the return code of the executed subprocess
    :rtype: int
    """
    if os.name == 'nt':
        process = subprocess.Popen(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout = process.stdout
    else:
        master, slave = os.openpty()
        process = subprocess.Popen(
            shlex.split(cmd, posix=True),
            stdout=slave,
            stderr=slave
        )
        stdout = os.fdopen(master)
        os.close(slave)

    def kill(process_):
        """Kill the specified process on Timer completion"""
        try:
            process_.kill()
        except OSError:
            pass

    # python 2-3 agnostic process timer
    timer = Timer(timeout, kill, [process])
    timer.setDaemon(True)
    timer.start()

    while process.returncode is None:
        try:
            if os.name == 'nt':
                line = stdout.readline()
                # windows gives readline() raw stdout as a b''
                # need to decode it
                line = line.decode("utf-8")
                if line:  # ignore empty strings and None
                    callback(line.rstrip())
            else:
                while True:
                    line = stdout.readline()
                    if not line:
                        break
                    callback(line.rstrip())
        except (IOError, OSError):
            # This seems to happen on some platforms, including TravisCI.
            # It seems like it's ok to just let this pass here, you just
            # won't get as nice feedback.
            pass
        if not timer.is_alive():
            raise TimeoutError(
                "subprocess running command '{}' timed out after {} seconds".format(
                    cmd, timeout))
        process.poll()

    # we have returned from the subprocess cancel the timer if it is running
    timer.cancel()

    return process.returncode


def tests_pass(config):
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    def feedback(line):
        if not config.swallow_output:
            print(line)
        config.print_progress()

    returncode = popen_streaming_output(config.test_command, feedback,
                                        timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def time_test_suite(swallow_output, test_command, using_testmon):
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
    if cached_time is not None:
        print(
            '1. Using cached time for baseline tests, to run baseline again delete the cache file')
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
        raise RuntimeError(
            "Tests don't run cleanly without mutations. Test command was: %s\n\nOutput:\n\n%s" % (
            test_command, '\n'.join(output)))

    print(' Done')

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed


class Config(object):
    def __init__(self, swallow_output, test_command, exclude_callback,
                 baseline_time_elapsed, test_time_multiplier, test_time_base,
                 backup, dict_synonyms, total, using_testmon, cache_only,
                 tests_dirs, hash_of_tests):
        self.swallow_output = swallow_output
        self.test_command = test_command
        self.exclude_callback = exclude_callback
        self.baseline_time_elapsed = baseline_time_elapsed
        self.test_time_multipler = test_time_multiplier
        self.test_time_base = test_time_base
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
        print_status('%s/%s  🎉 %s  ⏰ %s  🤔 %s  🙁 %s' % (
        self.progress, self.total, self.killed_mutants,
        self.surviving_mutants_timeout, self.suspicious_mutants,
        self.surviving_mutants))


def compute_exit_code(mutants, exception=None):
    """Compute an exit code for mutmut mutation testing

    The following output status codes are available for muckup:
     * 0 if all mutants were killed (OK_KILLED)
     * 1 if a fatal error occurred
     * 2 if one or more mutants survived (BAD_SURVIVED)
     * 4 if one or more mutants timed out (BAD_TIMEOUT)
     * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)
     Exit codes 1 to 8 will be bit-ORed so that it is possible to know what
     different mutant statuses occurred during mutation testing.

    :param mutants: The list of tested mutants.
    :type mutants: list[Mutant]

    :param exception: If an exception was thrown during test execution
        it should be given here.
    :type exception: Exception

    :return: integer noting the exit code of the mutation tests.
    :rtype: int
    """
    code = 0
    if exception is not None:
        code = code | 1
    if any(mutant.status == BAD_SURVIVED for mutant in mutants):
        code = code | 2
    if any(mutant.status == BAD_TIMEOUT for mutant in mutants):
        code = code | 4
    if any(mutant.status == OK_SUSPICIOUS for mutant in mutants):
        code = code | 8
    return code


class Runner:

    def __init__(self, test_command, swallow_output=True,
                 using_testmon=False, baseline_test_time=None):
        """Construct a MutationTestRunner

        :param test_command:
        :type test_command: str

        :param swallow_output:
        :type swallow_output: bool

        :param using_testmon:
        :type using_testmon: bool

        :param baseline_test_time:
        :type baseline_test_time: float or None
        """
        self.test_command = test_command
        self.swallow_output = swallow_output
        self.using_testmon = using_testmon
        self.baseline_test_time = baseline_test_time

    def run_mutation_tests(self, mutants):
        """

        :param mutants:
        :type mutants: list[Mutant]
        :return:
        """
        print("{:=^79}".format(" Starting Mutation Tests "))
        print("Using test runner: {}".format(self.test_command))
        if self.baseline_test_time is None:
            self.time_test_suite()
        for mutant in mutants:
            # original, mutation = mutant.mutation_original_pair
            # print("{}['{}'->'{}'] ".format(mutant.source_filename, original, mutation), end='')
            self.test_mutant(mutant)
            print(mutant.status)
            self.print_progress(mutants)
        return mutants

    def test_mutant(self, mutant):
        """Test a given mutant and set its respective status on completion

        :param mutant: The mutant to test.
        :type mutant: Mutant
        """
        if mutant.status != UNTESTED:
            return
        try:
            mutant.apply()
            start = time()
            try:
                survived = self.run_test(timeout=self.baseline_test_time * 10)
            except TimeoutError:
                mutant.status = BAD_TIMEOUT
            else:
                if time() - start > self.baseline_test_time * 2:
                    mutant.status = OK_SUSPICIOUS
                elif survived:
                    mutant.status = BAD_SURVIVED
                else:
                    mutant.status = OK_KILLED
        finally:
            mutant.revert()

    def time_test_suite(self):
        """Compute the unmutated test suite's execution time

        :raise RuntimeError: If the unmutated tests fail.
            Mutation testing cannot be done on a failing test suite.
        """
        start_time = time()
        green_suite = self.run_test()
        if green_suite:
            self.baseline_test_time = time() - start_time
            print("Ran unmutated test suite in {} seconds".format(self.baseline_test_time))
        else:
            raise RuntimeError("Mutation tests require a green suite")

    def run_test(self, timeout=None):
        """Run the test command and obtain a boolean noting if the test suite
        has passed

        :return: boolean noting if the test suite has passed
        :rtype: bool
        """
        if self.using_testmon:
            copy('.testmondata-initial', '.testmondata')

        def feedback(line):
            if not self.swallow_output:
                print(line)

        returncode = popen_streaming_output(
            cmd=self.test_command,
            callback=feedback,
            timeout=timeout
        )
        return returncode == 0 or (self.using_testmon and returncode == 5)

    def print_progress(self, mutants):
        pass
        # TODO:
        # print_status('%s/%s  🎉 %s  ⏰ %s  🤔 %s  🙁 %s' % (
        # self.progress, self.total, self.killed_mutants,
        # self.surviving_mutants_timeout, self.suspicious_mutants,
        # self.surviving_mutants))

