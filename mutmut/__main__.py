#!/usr/bin/env python
# -*- coding: utf-8 -*-

import fnmatch
import itertools
import os
import shlex
import subprocess
import sys
import traceback
from configparser import ConfigParser, NoOptionError, NoSectionError
from functools import wraps
from io import open
from os.path import isdir, exists
from shutil import move, copy
from threading import Timer
from time import time
from typing import List

import click
from glob2 import glob

from mutmut import mutate_file, Context, list_mutations, __version__, \
    BAD_TIMEOUT, OK_SUSPICIOUS, BAD_SURVIVED, OK_KILLED, UNTESTED, MutationID
from mutmut.cache import register_mutants, update_mutant_status, \
    print_result_cache, cached_mutation_status, hash_of_tests, \
    filename_and_mutation_id_from_pk, cached_test_time, set_cached_test_time, \
    update_line_numbers, print_result_cache_junitxml, get_unified_diff

spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')


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


def guess_paths_to_mutate():
    """Guess the path to source code to mutate

    :rtype: str
    """
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
        'or by adding "paths_to_mutate=code_dir" in setup.cfg to the [mutmut] section.')


def do_apply(mutation_pk, dict_synonyms, backup):
    """Apply a specified mutant to the source code

    :param mutation_pk: mutmut cache primary key of the mutant to apply
    :type mutation_pk: str

    :param dict_synonyms: list of synonym keywords for a python dictionary
    :type dict_synonyms: list[str]

    :param backup: if :obj:`True` create a backup of the source file
        before applying the mutation
    :type backup: bool
    """
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))

    update_line_numbers(filename)

    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )


null_out = open(os.devnull, 'w')


class Config(object):
    def __init__(self, swallow_output, test_command, covered_lines_by_filename,
                 baseline_time_elapsed, test_time_multiplier, test_time_base,
                 backup, dict_synonyms, total, using_testmon, cache_only,
                 tests_dirs, hash_of_tests, pre_mutation, post_mutation,
                 coverage_data):
        self.swallow_output = swallow_output
        self.test_command = test_command
        self.covered_lines_by_filename = covered_lines_by_filename
        self.baseline_time_elapsed = baseline_time_elapsed
        self.test_time_multipler = test_time_multiplier
        self.test_time_base = test_time_base
        self.backup = backup
        self.dict_synonyms = dict_synonyms
        self.total = total
        self.using_testmon = using_testmon
        self.cache_only = cache_only
        self.tests_dirs = tests_dirs
        self.hash_of_tests = hash_of_tests
        self.post_mutation = post_mutation
        self.pre_mutation = pre_mutation
        self.coverage_data = coverage_data


class Progress(object):
    def __init__(self):
        self.progress = 0
        self.skipped = 0
        self.killed_mutants = 0
        self.surviving_mutants = 0
        self.surviving_mutants_timeout = 0
        self.suspicious_mutants = 0

    def print(self, total):
        print_status('{}/{}  🎉 {}  ⏰ {}  🤔 {}  🙁 {}'.format(self.progress, total, self.killed_mutants, self.surviving_mutants_timeout, self.suspicious_mutants, self.surviving_mutants))


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('command', nargs=1, required=False)
@click.argument('argument', nargs=1, required=False)
@click.argument('argument2', nargs=1, required=False)
@click.option('--paths-to-mutate', type=click.STRING)
@click.option('--paths-to-exclude', type=click.STRING, required=False)
@click.option('--backup/--no-backup', default=False)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--use-patch-file', help='Only mutate lines added/changed in the given patch file')
@click.option('--tests-dir')
@click.option('-m', '--test-time-multiplier', default=2.0, type=float)
@click.option('-b', '--test-time-base', default=0.0, type=float)
@click.option('-s', '--swallow-output', help='turn off output capture', is_flag=True)
@click.option('--dict-synonyms')
@click.option('--cache-only', is_flag=True, default=False)
@click.option('--version', is_flag=True, default=False)
@click.option('--suspicious-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@click.option('--untested-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@click.option('--pre-mutation')
@click.option('--post-mutation')
@config_from_setup_cfg(
    dict_synonyms='',
    paths_to_exclude='',
    runner='python -m pytest -x',
    tests_dir='tests/:test/',
    pre_mutation=None,
    post_mutation=None,
    use_patch_file=None,
)
def climain(command, argument, argument2, paths_to_mutate, backup, runner, tests_dir,
            test_time_multiplier, test_time_base,
            swallow_output, use_coverage, dict_synonyms, cache_only, version,
            suspicious_policy, untested_policy, pre_mutation, post_mutation,
            use_patch_file, paths_to_exclude):
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
    show [path to file]\n
        Show all mutation diffs for this file.\n
    junitxml\n
        Show a mutation diff with junitxml format.
    """
    if test_time_base is None:  # click sets the default=0.0 to None
        test_time_base = 0.0
    if test_time_multiplier is None:  # click sets the default=0.0 to None
        test_time_multiplier = 0.0
    sys.exit(main(command, argument, argument2, paths_to_mutate, backup, runner,
                  tests_dir, test_time_multiplier, test_time_base,
                  swallow_output, use_coverage, dict_synonyms, cache_only,
                  version, suspicious_policy, untested_policy, pre_mutation,
                  post_mutation, use_patch_file, paths_to_exclude))


def main(command, argument, argument2, paths_to_mutate, backup, runner, tests_dir,
         test_time_multiplier, test_time_base,
         swallow_output, use_coverage, dict_synonyms, cache_only, version,
         suspicious_policy, untested_policy, pre_mutation, post_mutation,
         use_patch_file, paths_to_exclude):
    """return exit code, after performing an mutation test run.

    :return: the exit code from executing the mutation tests
    :rtype: int
    """
    if version:
        print("mutmut version {}".format(__version__))
        return 0

    if use_coverage and use_patch_file:
        raise click.BadArgumentUsage("You can't combine --use-coverage and --use-patch")

    valid_commands = ['run', 'results', 'apply', 'show', 'junitxml']
    if command not in valid_commands:
        raise click.BadArgumentUsage('{} is not a valid command, must be one of {}'.format(command, ', '.join(valid_commands)))

    if command == 'results' and argument:
        raise click.BadArgumentUsage('The {} command takes no arguments'.format(command))

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    if command in ('show', 'diff'):
        if not argument:
            print_result_cache()
            return 0

        if argument == 'all':
            print_result_cache(show_diffs=True, dict_synonyms=dict_synonyms, print_only_filename=argument2)
            return 0

        if os.path.isfile(argument):
            print_result_cache(show_diffs=True, only_this_file=argument)
            return 0

        print(get_unified_diff(argument, dict_synonyms))
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

    if paths_to_mutate is None:
        paths_to_mutate = guess_paths_to_mutate()

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

Results are stored in .mutmut-cache.
Print found mutants with `mutmut results`.

Legend for output:
🎉 Killed mutants.   The goal is for everything to end up in this bucket.
⏰ Timeout.          Test suite took 10 times as long as the baseline so were killed.
🤔 Suspicious.       Tests took a long time, but not long enough to be fatal.
🙁 Survived.         This means your tests needs to be expanded.
""")
    baseline_time_elapsed = time_test_suite(
        swallow_output=not swallow_output,
        test_command=runner,
        using_testmon=using_testmon
    )

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    # if we're running in a mode with externally whitelisted lines
    covered_lines_by_filename = None
    coverage_data = None
    if use_coverage or use_patch_file:
        covered_lines_by_filename = {}
        if use_coverage:
            coverage_data = read_coverage_data()
            check_coverage_data_filepaths(coverage_data)
        else:
            assert use_patch_file
            covered_lines_by_filename = read_patch_data(use_patch_file)

    if command != 'run':
        raise click.BadArgumentUsage("Invalid command {}".format(command))

    mutations_by_file = {}

    paths_to_exclude = paths_to_exclude or ''
    if paths_to_exclude:
        paths_to_exclude = [path.strip() for path in paths_to_exclude.split(',')]

    config = Config(
        total=0,  # we'll fill this in later!
        swallow_output=not swallow_output,
        test_command=runner,
        covered_lines_by_filename=covered_lines_by_filename,
        coverage_data=coverage_data,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=backup,
        dict_synonyms=dict_synonyms,
        using_testmon=using_testmon,
        cache_only=cache_only,
        tests_dirs=tests_dirs,
        hash_of_tests=hash_of_tests(tests_dirs),
        test_time_multiplier=test_time_multiplier,
        test_time_base=test_time_base,
        pre_mutation=pre_mutation,
        post_mutation=post_mutation,
    )

    if argument is None:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs, paths_to_exclude):
                update_line_numbers(filename)
                add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config)
    else:
        filename, mutation_id = filename_and_mutation_id_from_pk(int(argument))
        mutations_by_file[filename] = [mutation_id]

    config.total = sum(len(mutations) for mutations in mutations_by_file.values())

    print()
    print('2. Checking mutants')
    progress = Progress()

    try:
        run_mutation_tests(config=config, progress=progress, mutations_by_file=mutations_by_file)
    except Exception as e:
        traceback.print_exc()
        return compute_exit_code(progress, e)
    else:
        return compute_exit_code(progress)
    finally:
        print()  # make sure we end the output with a newline


def check_coverage_data_filepaths(coverage_data):
    for filepath in coverage_data._lines:
        if not os.path.exists(filepath):
            raise ValueError('Filepaths in .coverage not recognized, try recreating the .coverage file manually.')


def get_mutations_by_file_from_cache(mutation_pk):
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))
    return {filename: [mutation_id]}


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
    if os.name == 'nt':  # pragma: no cover
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
            if os.name == 'nt':  # pragma: no cover
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


def tests_pass(config: Config, callback) -> bool:
    """
    :return: :obj:`True` if the tests pass, otherwise :obj:`False`
    """
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    returncode = popen_streaming_output(config.test_command, callback, timeout=config.baseline_time_elapsed * 10)
    return returncode == 0 or (config.using_testmon and returncode == 5)


def run_mutation(config: Config, filename: str, mutation_id: MutationID, callback) -> str:
    """
    :return: (computed or cached) status of the tested mutant, one of mutant_statuses
    """
    context = Context(
        mutation_id=mutation_id,
        filename=filename,
        dict_synonyms=config.dict_synonyms,
        config=config,
    )

    cached_status = cached_mutation_status(filename, mutation_id, config.hash_of_tests)

    if cached_status != UNTESTED:
        return cached_status

    if config.pre_mutation:
        result = subprocess.check_output(config.pre_mutation, shell=True).decode().strip()
        if result and not config.swallow_output:
            print(result)

    try:
        mutate_file(
            backup=True,
            context=context
        )
        start = time()
        try:
            survived = tests_pass(config=config, callback=callback)
        except TimeoutError:
            return BAD_TIMEOUT

        time_elapsed = time() - start
        if not survived and time_elapsed > config.test_time_base + (config.baseline_time_elapsed * config.test_time_multipler):
            return OK_SUSPICIOUS

        if survived:
            return BAD_SURVIVED
        else:
            return OK_KILLED
    finally:
        move(filename + '.bak', filename)

        if config.post_mutation:
            result = subprocess.check_output(config.post_mutation, shell=True).decode().strip()
            if result and not config.swallow_output:
                print(result)


def run_mutation_tests_for_file(config: Config, progress: Progress, file_to_mutate: str, mutations: List[MutationID]) -> None:
    """
    :type config: Config
    :type progress: Progress
    :type file_to_mutate: str
    :type mutations: list[MutationID]
    """
    def feedback(line):
        if not config.swallow_output:
            print(line)
        progress.print(total=config.total)

    for mutation_id in mutations:
        status = run_mutation(config, file_to_mutate, mutation_id, callback=feedback)
        update_mutant_status(file_to_mutate, mutation_id, status, config.hash_of_tests)

        if status == BAD_SURVIVED:
            progress.surviving_mutants += 1
        elif status == BAD_TIMEOUT:
            progress.surviving_mutants_timeout += 1
        elif status == OK_KILLED:
            progress.killed_mutants += 1
        elif status == OK_SUSPICIOUS:
            progress.suspicious_mutants += 1
        else:
            raise ValueError('Unknown status returned from run_mutation: {}'.format(status))

        progress.progress += 1
        progress.print(total=config.total)


def run_mutation_tests(config, progress, mutations_by_file):
    """
    :type config: Config
    :type progress: Progress
    :type mutations_by_file: dict[str, list[MutationID]]
    """
    for file_to_mutate, mutations in mutations_by_file.items():
        progress.print(total=config.total)

        run_mutation_tests_for_file(config, progress, file_to_mutate, mutations)


def read_coverage_data():
    """
    :rtype: CoverageData or None
    """
    try:
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        from coverage import Coverage
    except ImportError as e:
        raise ImportError('The --use-coverage feature requires the coverage library. Run "pip install --force-reinstall mutmut[coverage]"') from e
    cov = Coverage('.coverage')
    cov.load()
    return cov.get_data()


def read_patch_data(patch_file_path):
    try:
        # noinspection PyPackageRequirements
        import whatthepatch
    except ImportError as e:
        raise ImportError('The --use-patch feature requires the whatthepatch library. Run "pip install --force-reinstall mutmut[patch]"') from e
    with open(patch_file_path) as f:
        diffs = whatthepatch.parse_patch(f.read())

    return {
        diff.header.new_path: {change.new for change in diff.changes if change.old is None}
        for diff in diffs
    }


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
        raise RuntimeError("Tests don't run cleanly without mutations. Test command was: {}\n\nOutput:\n\n{}".format(test_command, '\n'.join(output)))

    print('Done')

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, dict_synonyms, config):
    """
    :type mutations_by_file: dict[str, list[MutationID]]
    :type filename: str
    :type exclude: Callable[[Context], bool]
    :type dict_synonyms: list[str]
    """
    with open(filename) as f:
        source = f.read()
    context = Context(
        source=source,
        filename=filename,
        config=config,
        dict_synonyms=dict_synonyms,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        register_mutants(mutations_by_file)
    except Exception as e:
        raise RuntimeError('Failed while creating mutations for {}, for line "{}"'.format(context.filename, context.current_source_line)) from e


def python_source_files(path, tests_dirs, paths_to_exclude=None):
    """Attempt to guess where the python source files to mutate are and yield
    their paths

    :param path: path to a python source file or package directory
    :type path: str

    :param tests_dirs: list of directory paths containing test files
        (we do not want to mutate these!)
    :type tests_dirs: list[str]

    :param paths_to_exclude: list of UNIX filename patterns to exclude
    :type paths_to_exclude: list[str]

    :return: generator listing the paths to the python source files to mutate
    :rtype: Generator[str, None, None]
    """
    paths_to_exclude = paths_to_exclude or []
    if isdir(path):
        for root, dirs, files in os.walk(path, topdown=True):
            for exclude_pattern in paths_to_exclude:
                dirs[:] = [d for d in dirs if not fnmatch.fnmatch(d, exclude_pattern)]
                files[:] = [f for f in files if not fnmatch.fnmatch(f, exclude_pattern)]

            dirs[:] = [d for d in dirs if os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def compute_exit_code(progress, exception=None):
    """Compute an exit code for mutmut mutation testing

    The following exit codes are available for mutmut:
     * 0 if all mutants were killed (OK_KILLED)
     * 1 if a fatal error occurred
     * 2 if one or more mutants survived (BAD_SURVIVED)
     * 4 if one or more mutants timed out (BAD_TIMEOUT)
     * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)

     Exit codes 1 to 8 will be bit-ORed so that it is possible to know what
     different mutant statuses occurred during mutation testing.

    :param exception:
    :type exception: Exception
    :param progress:
    :type progress: Progress

    :return: integer noting the exit code of the mutation tests.
    :rtype: int
    """
    code = 0
    if exception is not None:
        code = code | 1
    if progress.surviving_mutants > 0:
        code = code | 2
    if progress.surviving_mutants_timeout > 0:
        code = code | 4
    if progress.suspicious_mutants > 0:
        code = code | 8
    return code


if __name__ == '__main__':
    climain()
