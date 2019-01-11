#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import itertools
import os
import shlex
import subprocess
import sys
import traceback
from functools import wraps
from io import open
from os.path import isdir, exists
from shutil import move, copy
from threading import Timer
from time import time

import click
from glob2 import glob

from mutmut import mutate_file, Context, list_mutations, __version__, \
    BAD_TIMEOUT, OK_SUSPICIOUS, BAD_SURVIVED, OK_KILLED, UNTESTED, MutationID
from mutmut.cache import hash_of_tests
from mutmut.cache import register_mutants, set_cached_mutant_status, \
    print_result_cache, get_cached_mutation_status, \
    filename_and_mutation_id_from_pk, cached_test_time, set_cached_test_time, \
    update_line_numbers, print_result_cache_junitxml, get_unified_diff

spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')

if sys.version_info >= (3, 5):   # pragma: no cover (python 2 specific)
    # add tying library for doc improvements
    from typing import Generator

if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    # noinspection PyCompatibility,PyUnresolvedReferences
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError
    # This little hack is needed to get the click tester working on python 2.7
    orig_print = print

    def print(x='', **kwargs):
        x = x.decode("utf-8")
        orig_print(x.encode("utf-8"), **kwargs)

    class TimeoutError(OSError):
        """Defining TimeoutError for Python 2 compatibility"""
else:
    # noinspection PyUnresolvedReferences,PyCompatibility
    from configparser import ConfigParser, NoOptionError, NoSectionError
    TimeoutError = TimeoutError


# decorator
def config_from_setup_cfg(**defaults):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            config_parser = ConfigParser()
            config_parser.read('setup.cfg')

            def s(key, default):
                try:
                    return config_parser.get('mutmut', key)
                except (NoOptionError, NoSectionError):
                    return default

            for k in list(kwargs.keys()):
                if not kwargs[k]:
                    kwargs[k] = s(k, defaults.get(k))
            f(*args, **kwargs)

        return wrapper
    return decorator


# this function is stolen and modified from tqdm
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


def get_or_guess_paths_to_mutate(paths_to_mutate):
    """

    :param paths_to_mutate:
    :type paths_to_mutate: str

    :return:
    :rtype: list[str] or str
    """
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
            raise FileNotFoundError('Could not figure out where the code to mutate is. Please specify it on the command line like "mutmut code_dir" or by adding "paths_to_mutate=code_dir" in setup.cfg under the section [mutmut]')
    else:
        return paths_to_mutate


def do_apply(mutation_pk, dict_synonyms, backup):
    """Apply a specified mutant to the source code

    :param mutation_pk:
    :type mutation_pk: str

    :param dict_synonyms:
    :type dict_synonyms: list[str]

    :param backup:
    :type backup: bool
    """
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))
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
        raise RuntimeError('No mutations performed. Are you sure the index is not too big?')


null_out = open(os.devnull, 'w')


class Config(object):
    def __init__(self, swallow_output, test_command, exclude_callback,
                 baseline_time_elapsed, test_time_multiplier, test_time_base,
                 backup, dict_synonyms, total, using_testmon, cache_only,
                 tests_dirs, hash_of_tests):
        """

        :param swallow_output:
        :type swallow_output: bool

        :param test_command:
        :type test_command: str

        :param exclude_callback:
        :type exclude_callback: Callable[[Context], bool]

        :param baseline_time_elapsed:
        :type baseline_time_elapsed: float

        :param test_time_multiplier:
        :type test_time_multiplier: float

        :param test_time_base:
        :type test_time_base: float

        :param backup:
        :type backup: bool

        :param dict_synonyms:
        :type dict_synonyms: list[str]

        :param total:
        :type total: int

        :param using_testmon:
        :type using_testmon: bool

        :param cache_only:
        :type cache_only: bool

        :param tests_dirs:
        :type tests_dirs: list[str]

        :param hash_of_tests:
        :type hash_of_tests: str
        """
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
        print_status('%s/%s  🎉 %s  ⏰ %s  🤔 %s  🙁 %s' % (self.progress, self.total, self.killed_mutants, self.surviving_mutants_timeout, self.suspicious_mutants, self.surviving_mutants))


DEFAULT_TESTS_DIR = 'tests/:test/'


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('command', nargs=1, required=False)
@click.argument('argument', nargs=1, required=False)
@click.option('--paths-to-mutate', type=click.STRING)
@click.option('--backup/--no-backup', default=False)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--tests-dir')
@click.option('-m', '--test-time-multiplier', default=2.0, type=float)
@click.option('-b', '--test-time-base', default=0.0, type=float)
@click.option('-s', '--swallow-output', help='turn off output capture', is_flag=True)
@click.option('--dict-synonyms')
@click.option('--cache-only', is_flag=True, default=False)
@click.option('--version', is_flag=True, default=False)
@click.option('--suspicious-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@click.option('--untested-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@config_from_setup_cfg(
    dict_synonyms='',
    runner='python -m pytest -x',
    tests_dir=DEFAULT_TESTS_DIR,
)
def climain(command, argument, paths_to_mutate, backup, runner, tests_dir,
            test_time_multiplier, test_time_base,
            swallow_output, use_coverage, dict_synonyms, cache_only, version,
            suspicious_policy, untested_policy):
    """
commands:\n
    run [mutation id]\n
        Runs mutmut. You probably want to start with just trying this. If you supply a mutation ID mutmut will check just this mutant.\n
    results\n
        Print the results.\n
    apply [mutation id]\n
        Apply a mutation on disk.\n
    show [mutation id]\n
        Show a mutation diff.\n
    """
    if test_time_base is None:  # click sets the default=0.0 to None
        test_time_base = 0.0
    if test_time_multiplier is None:  # click sets the default=0.0 to None
        test_time_multiplier = 0.0
    sys.exit(main(command, argument, paths_to_mutate, backup, runner,
                  tests_dir, test_time_multiplier, test_time_base,
                  swallow_output, use_coverage, dict_synonyms, cache_only,
                  version, suspicious_policy, untested_policy))


def main(command, argument, paths_to_mutate, backup, runner, tests_dir,
         test_time_multiplier, test_time_base,
         swallow_output, use_coverage, dict_synonyms, cache_only, version,
         suspicious_policy,
         untested_policy):
    """return exit code, after performing an mutation test run.

    # TODO possibly rework
    :param command:
    :type command: str

    :param argument:
    :type argument: str

    :param paths_to_mutate:
    :type paths_to_mutate:

    :param backup:
    :type backup: bool

    :param runner:
    :type runner: str

    # TODO: maybe rework type
    :param tests_dir:
    :type tests_dir: str

    :param test_time_multiplier:
    :type test_time_multiplier: float

    :param test_time_base:
    :type test_time_base: float

    :param swallow_output:
    :type swallow_output: bool

    :param use_coverage:
    :type use_coverage: bool

    TODO: maybe rework how dict_synonyms works
    :param dict_synonyms:
    :type dict_synonyms: str

    :param cache_only:
    :type cache_only: bool

    :param version:
    :type version: bool

    :param suspicious_policy:
    :type suspicious_policy: str

    :param untested_policy:
    :type untested_policy: str

    :return: the exit code from executing the mutation tests
    :rtype: int
    """
    if version:
        print("mutmut version %s" % __version__)
        return 0

    valid_commands = ['run', 'results', 'apply', 'show', 'junitxml']
    if command not in valid_commands:
        raise click.BadArgumentUsage('%s is not a valid command, must be one of %s' % (command, ', '.join(valid_commands)))

    if command == 'results' and argument:
        raise click.BadArgumentUsage('The %s command takes no arguments' % command)

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if command in ('show', 'diff'):
        if not argument:
            print_result_cache()
            return 0

        print(get_unified_diff(int(argument), dict_synonyms))
        return 0

    if use_coverage and not exists('.coverage'):
        raise FileNotFoundError('No .coverage file found. You must generate a coverage file to use this feature.')

    if command == 'results':
        print_result_cache()
        return 0

    if command == 'junitxml':
        print_result_cache_junitxml(dict_synonyms, suspicious_policy, untested_policy)
        return 0

    if command == 'apply':
        do_apply(argument, dict_synonyms, backup)
        return 0

    paths_to_mutate = get_or_guess_paths_to_mutate(paths_to_mutate)

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise click.BadOptionUsage('--paths-to-mutate', 'You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')

    tests_dirs = []
    for p in tests_dir.split(':'):
        tests_dirs.extend(glob(p, recursive=True))

    for p in paths_to_mutate:
        for pt in tests_dir.split(':'):
            tests_dirs.extend(glob(p + '/**/' + pt, recursive=True))
    del tests_dir

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    using_testmon = '--testmon' in runner

    print("""
- Mutation testing starting - 

These are the steps:
1. A full test suite run will be made to make sure we 
   can run the tests successfully and we know how long 
   it takes (to detect infinite loops for example)
2. Mutants will be generated and checked

Mutants are written to the cache in the .mutmut-cache 
directory. Print found mutants with `mutmut results`.

Legend for output:
🎉 Killed mutants. The goal is for everything to end up in this bucket. 
⏰ Timeout. Test suite took 10 times as long as the baseline so were killed.  
🤔 Suspicious. Tests took a long time, but not long enough to be fatal. 
🙁 Survived. This means your tests needs to be expanded. 
""")
    baseline_time_elapsed = time_test_suite(
        swallow_output=not swallow_output,
        test_command=runner,
        using_testmon=using_testmon
    )

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    if not use_coverage:
        def _exclude(context):
            """

            :param context:
            :type context: Context

            :return:
            :rtype: bool
            """
            return False
    else:
        covered_lines_by_filename = {}
        coverage_data = read_coverage_data(use_coverage)

        def _exclude(context):
            """

            :param context:
            :type context: Context

            :return:
            :rtype: bool
            """
            try:
                covered_lines = covered_lines_by_filename[context.filename]
            except KeyError:
                covered_lines = coverage_data.lines(os.path.abspath(context.filename))
                covered_lines_by_filename[context.filename] = covered_lines

            if covered_lines is None:
                return True
            current_line = context.current_line_index + 1
            if current_line not in covered_lines:
                return True
            return False

    if command != 'run':
        raise click.BadArgumentUsage("Invalid command %s" % command)

    mutations_by_file = {}

    if argument is None:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs):
                update_line_numbers(filename)
                add_mutations_by_file(mutations_by_file, filename, _exclude, dict_synonyms)
    else:
        filename, mutation_id = filename_and_mutation_id_from_pk(int(argument))
        mutations_by_file[filename] = [mutation_id]

    total = sum(len(mutations) for mutations in mutations_by_file.values())

    print()
    print('2. Checking mutants')
    config = Config(
        swallow_output=not swallow_output,
        test_command=runner,
        exclude_callback=_exclude,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=backup,
        dict_synonyms=dict_synonyms,
        total=total,
        using_testmon=using_testmon,
        cache_only=cache_only,
        tests_dirs=tests_dirs,
        hash_of_tests=hash_of_tests(tests_dirs),
        test_time_multiplier=test_time_multiplier,
        test_time_base=test_time_base,
    )

    try:
        run_mutation_tests(config=config, mutations_by_file=mutations_by_file)
    except Exception as e:
        traceback.print_exc()
        return compute_exit_code(config, e)
    else:
        return compute_exit_code(config)


def popen_streaming_output(cmd, callback, timeout=None):
    """Open a subprocess and stream its output without hard-blocking.

    :param cmd: command to execute within the subprocess
    :type cmd: str

    :param callback: function that intakes the subprocess' stdout line by line.
        It is called for each line received from the subprocess' stdout stream.
    :type callback: Callable[[Context], bool]

    :param timeout: timeout time of the subprocess
    :type timeout: float

    :raises TimeoutError: if the subprocess' execution time exceeds
        the timeout time

    :return: return code of the executed subprocess
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
        """Kill the specified process on Timer completion

        :type process_: subprocess.Popen
        """
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
            raise TimeoutError("subprocess running command '{}' timed out after {} seconds".format(cmd, timeout))
        process.poll()

    # we have returned from the subprocess cancel the timer if it is running
    timer.cancel()

    return process.returncode


def tests_pass(config):
    """Run tests specified by the given `mutmut run` config

    :param config: the `mutmut run` config
    :type config: Config

    :return: :obj:`True` if the tests passed, otherwise :obj:`False`
    :rtype: bool
    """
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    def feedback(line):
        if not config.swallow_output:
            print(line)
        config.print_progress()

    returncode = popen_streaming_output(config.test_command, feedback, timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def run_mutation(config, filename, mutation_id):
    """Obtain a mutant's status either by obtaining it from the cache
    or if the mutant's status is untested execute the tests for the mutant

    :param config: the `mutmut run` config
    :type config: Config

    :param filename: path to the source file to mutate
    :type filename: str

    :param mutation_id: id of the mutant to run
    :type mutation_id: MutationID

    :return: status of the mutation
    :rtype: str
    """
    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        dict_synonyms=config.dict_synonyms,
        config=config,
    )

    cached_status = get_cached_mutation_status(filename, mutation_id, config.hash_of_tests)
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
        start = time()
        try:
            survived = tests_pass(config)
        except TimeoutError:
            context.config.surviving_mutants_timeout += 1
            return BAD_TIMEOUT

        time_elapsed = time() - start
        if time_elapsed > config.test_time_base + (config.baseline_time_elapsed * config.test_time_multipler):
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
    """

    :param config:
    :type config: Config

    :param file_to_mutate:
    :type file_to_mutate: str

    :param mutations:
    :type mutations: list[MutationID]
    """
    for mutation_id in mutations:
        status = run_mutation(config, file_to_mutate, mutation_id)
        set_cached_mutant_status(file_to_mutate, mutation_id, status, config.hash_of_tests)
        config.progress += 1
        config.print_progress()


def run_mutation_tests(config, mutations_by_file):
    """
    :type config: Config
    :type mutations_by_file: dict[str, list[MutationID]]
    """
    for file_to_mutate, mutations in mutations_by_file.items():
        config.print_progress()

        run_mutation_tests_for_file(config, file_to_mutate, mutations)


def read_coverage_data(use_coverage):
    """

    :param use_coverage:
    :type use_coverage: bool

    :return:
    :rtype: coverage.CoverageData or None
    """
    if use_coverage:
        print('Using coverage data from .coverage file')
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        from coverage import Coverage
        return Coverage('.coverage').get_data()
    else:
        return None


def time_test_suite(swallow_output, test_command, using_testmon):
    """Execute a test suite specified by ``test_command`` and record
    the time it took to execute the test suite as a floating point number

    :param swallow_output: if :obj:`True` test stdout will be not be printed
    :type swallow_output: bool

    :param test_command:
    :type test_command: str

    :param using_testmon: if :obj:`True` the test return code evaluation will
        accommodate for ``pytest-testmon``
    :type using_testmon: bool

    :return: execution time of the test suite as a floating point number
    :rtype: float
    """
    cached_time = cached_test_time()
    if cached_time is not None:
        print('1. Using cached time for baseline tests, to run baseline again delete the cache file')
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
        raise RuntimeError("Tests don't run cleanly without mutations. Test command was: %s\n\nOutput:\n\n%s" % (test_command, '\n'.join(output)))

    print(' Done')

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms):
    """

    :param mutations_by_file:
    :type mutations_by_file: dict[str, list[MutationID]]

    :param filename:
    :type filename: str

    :param exclude:
    :type exclude: Callable[[Context], bool]

    :param dict_synonyms: list of synonyms of python dictionary objects
    :type dict_synonyms: list[str]
    :return:
    """
    with open(filename) as f:
        source = f.read()
    context = Context(
        source=source,
        filename=filename,
        exclude=exclude,
        dict_synonyms=dict_synonyms,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        register_mutants(mutations_by_file)
    except Exception as e:
        raise RuntimeError('Failed while creating mutations for %s, for line "%s"' % (context.filename, context.current_source_line), e)


# TODO: check if used
def coverage_exclude_callback(context, use_coverage, coverage_data):
    """

    :param context:
    :type context: Context

    :param use_coverage:
    :type use_coverage: bool

    :param coverage_data:
    :type coverage_data: coverage.CoverageData

    :return:
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
    """Attempt to guess where the python source files to mutate are and yield
    their paths

    :param path:
    :type path: str

    :param tests_dirs: List of directory paths containing test files
        (we do not want to mutate these!)
    :type tests_dirs: list[str]

    :return: Generator specifying all the python source files to mutate are
    :rtype: Generator[str, None, None]
    """
    if isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def compute_exit_code(config, exception=None):
    """Compute an exit code for mutmut mutation testing

    The following exit codes are available for mutmut:
     * 0 if all mutants were killed (OK_KILLED)
     * 1 if a fatal error occurred
     * 2 if one or more mutants survived (BAD_SURVIVED)
     * 4 if one or more mutants timed out (BAD_TIMEOUT)
     * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)

     Exit codes 1 to 8 will be bit-ORed so that it is possible to know what
     different mutant statuses occurred during mutation testing.

    :param config:
    :type config: Config

    :param exception:
    :type exception: Exception

    :return: integer noting the exit code of the mutation tests.
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


if __name__ == '__main__':
    climain()
