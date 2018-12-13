#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Mutation testing execution runner"""

import shlex
import subprocess
import sys
from datetime import datetime
from shutil import move, copy

from mutmut.cache import set_cached_test_time, get_cached_test_time, \
    get_cached_mutation_status, update_mutant_status, register_mutants, \
    get_filename_and_mutation_id_from_pk
from mutmut.mutators import mutate_file, Context, list_mutations
from mutmut.terminal import print_status
from threading import Timer

if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    class TimeoutError(OSError):
        """ Timeout expired.

        python2.7 does not have this exception class natively so we add it for
        simplicity.
        """

        def __init__(self, *args, **kwargs):  # real signature unknown
            pass
else:
    TimeoutError = TimeoutError


class Config(object):
    """Container for all the needed configuration for a mutation test run"""

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
        print_status(
            '%s/%s  🎉 %s  ⏰ %s  🤔 %s  🙁 %s' %
            (self.progress, self.total, self.killed_mutants,
             self.surviving_mutants_timeout, self.suspicious_mutants,
             self.surviving_mutants)
        )


def do_apply(mutation_pk, dict_synonyms, backup):
    filename, mutation_id = get_filename_and_mutation_id_from_pk(
        int(mutation_pk))
    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )
    if context.number_of_performed_mutations == 0:
        raise ValueError('ERROR: no mutations performed. '
                         'Are you sure the index is not too big?')


def add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms):
    """

    :param mutations_by_file:
    :type mutations_by_file: dict[str, list[MutationID]]

    :param filename: the file to create mutations in
    :type filename: str

    :param dict_synonyms:
    :type: TODO

    :param exclude:
    """
    context = Context(
        source=open(filename).read(),
        filename=filename,
        exclude=exclude,
        dict_synonyms=dict_synonyms,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        register_mutants(mutations_by_file)
    except Exception:
        print('Failed while creating mutations for %s, for line "%s"' % (
        context.filename, context.current_source_line))
        raise


def popen_streaming_output(cmd, callback, timeout=None):
    """Open a subprocess and stream its output without hard-blocking.

    :param cmd: the command to execute within the subprocess
    :type cmd: str

    :param callback: function to execute with the subprocess stdout output
    :param timeout: the timeout time for the processes' ``communication``
        call to complete
    :type timeout: float

    :raises TimeoutError: if the subprocesses' ``communication`` call times out

    :return: the return code of the executed subprocess
    :rtype: int
    """
    process = subprocess.Popen(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    def kill(p):
        try:
            p.kill()
        except OSError:
            pass  # ignore

    # python 2-3 agnostic process timer
    timer = Timer(timeout, kill, [process])
    timer.start()

    while process.returncode is None:
        try:
            output, errors = process.communicate()
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
        if not timer.is_alive():
            raise TimeoutError("subprocess timed out")

    # we have returned from the subprocess cancel the timer if it is running
    timer.cancel()

    return process.returncode


def run_mutation_tests(config, mutations_by_file):
    """
    :type config: Config
    :type mutations_by_file: dict[str, list[MutationID]]
    """
    for file_to_mutate, mutations in mutations_by_file.items():
        config.print_progress()

        run_mutation_tests_for_file(config, file_to_mutate, mutations)


def run_mutation_tests_for_file(config, file_to_mutate, mutations):
    """Run mutation tests for a given file

    :param config:
    :type config: Config

    :param file_to_mutate: path of the file to run mutation tests over
    :type file_to_mutate: str

    :param mutations:
    :type mutations: list[MutationID]
    """
    for mutation_id in mutations:
        status = run_mutation(config, file_to_mutate, mutation_id)
        update_mutant_status(file_to_mutate, mutation_id, status,
                             config.hash_of_tests)
        config.progress += 1
        config.print_progress()


def run_mutation(config, filename, mutation_id):
    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        dict_synonyms=config.dict_synonyms,
        config=config,
    )
    from mutmut.mutators import BAD_SURVIVED, BAD_TIMEOUT, OK_KILLED, \
        OK_SUSPICIOUS, UNTESTED

    cached_status = get_cached_mutation_status(filename, mutation_id,
                                               config.hash_of_tests)
    if cached_status == BAD_SURVIVED:
        config.surviving_mutants += 1
    elif cached_status == BAD_TIMEOUT:
        config.surviving_mutants_timeout += 1
    elif cached_status == OK_KILLED:
        config.killed_mutants += 1
    elif cached_status == OK_SUSPICIOUS:
        config.suspicious_mutants += 1
    else:
        assert cached_status == UNTESTED, cached_status

    config.print_progress()

    if cached_status != UNTESTED:
        return cached_status

    try:
        number_of_mutations_performed = mutate_file(
            backup=True,
            context=context
        )
        if number_of_mutations_performed <= 0:
            raise ValueError("no mutations preformed on file: {}".format(filename))

        start = datetime.now()
        try:
            survived = tests_pass(config)
        except TimeoutError:
            context.config.surviving_mutants_timeout += 1
            return BAD_TIMEOUT

        time_elapsed = datetime.now() - start
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


def tests_pass(config):
    """Run the test command and obtain a boolean noting if the test suite
    has passed

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
        config.print_progress()

    returncode = popen_streaming_output(config.test_command, feedback,
                                        timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def time_test_suite(swallow_output, test_command, using_testmon):
    cached_time = get_cached_test_time()
    if cached_time is not None:
        print(
            '1. Using cached time for baseline tests, to run baseline again delete the cache file')
        return cached_time

    print('1. Running tests without mutations')
    start_time = datetime.now()

    output = []

    def feedback(line):
        if not swallow_output:
            print(line)
        print_status('Running...')
        output.append(line)

    returncode = popen_streaming_output(test_command, feedback)

    if returncode == 0 or (using_testmon and returncode == 5):
        baseline_time_elapsed = (datetime.now() - start_time).total_seconds()
    else:
        raise RuntimeError(
            "Tests don't run cleanly without mutations. Test command was: %s\n\nOutput:\n\n%s" % (
            test_command, '\n'.join(output)))

    print(' Done')

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed
