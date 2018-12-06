#!/usr/bin/python
# -*- coding: utf-8 -*-
import datetime
import os
import subprocess
from os.path import isdir
from shutil import move, copy

from mutmut.cache import cached_mutation_status, update_mutant_status, \
    set_cached_test_time, register_mutants, cached_test_time
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
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    def feedback(line):
        if not config.swallow_output:
            print(line)
        config.print_progress()

    returncode = popen_streaming_output(config.test_command, feedback,
                                        timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def run_mutation(config, filename, mutation_id):
    context = MutationContext(
        mutate_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        config=config,
    )

    cached_status = cached_mutation_status(filename, mutation_id,
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


def run_mutation_tests_for_file(config, file_to_mutate, mutations):
    for mutation_id in mutations:
        status = run_mutation(config, file_to_mutate, mutation_id)
        update_mutant_status(file_to_mutate, mutation_id, status,
                             config.hash_of_tests)
        config.progress += 1


def fail_on_cache_only(config):
    if config.cache_only:
        print('\rFAILED: changes detected in cache only mode')
        exit(2)


def run_mutation_tests(config, mutations_by_file):
    """
    :type config: Config
    :type mutations_by_file: dict[str, list[tuple]]
    """
    for file_to_mutate, mutations in mutations_by_file.items():
        run_mutation_tests_for_file(config, file_to_mutate, mutations)


def read_coverage_data(use_coverage):
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
    cached_time = cached_test_time()
    if cached_time is not None:
        print(
            '1. Using cached time for baseline tests, to run baseline again delete the cache file')
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
    if use_coverage:
        measured_lines = coverage_data.lines(os.path.abspath(context.filename))
        if measured_lines is None:
            return True
        current_line = context.current_line_index + 1
        if current_line not in measured_lines:
            return True
    return False


def python_source_files(path, tests_dirs):
    if isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if
                       os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path
