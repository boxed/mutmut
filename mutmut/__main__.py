# coding=utf-8


import argparse
import os
import sys
from configparser import ConfigParser, NoOptionError, NoSectionError
from datetime import datetime
from functools import wraps
from io import open
from os.path import isdir, exists
from shutil import move, copy
from subprocess import Popen
from threading import Thread
from time import sleep

from glob2 import glob

from mutmut.cache import register_mutants, update_mutant_status, \
    print_result_cache, cached_mutation_status, \
    filename_and_mutation_id_from_pk, cached_test_time, set_cached_test_time
from mutmut.mutators import mutate_file, Context, list_mutations, BAD_TIMEOUT, \
    OK_SUSPICIOUS, BAD_SURVIVED, OK_KILLED, UNTESTED
from .cache import hash_of_tests


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
    context = Context(
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
        print('%s/%s  🎉 %s  ⏰ %s  🤔 %s  🙁 %s' % (
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
    parser.add_argument("--runner", default="pytest")
    parser.add_argument("--results", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--apply")
    parser.add_argument("--tests-dir", dest="tests_dir", default="tests")
    parser.add_argument("-s", action="store_true", dest="output_capture",
                        help="turn off output capture")
    parser.add_argument("--cache-only", action="store_true", dest="cache_only")
    return parser


# @click.command(context_settings=dict(help_option_names=['-h', '--help']))
# @click.argument('command', nargs=1, required=False)
# @click.argument('argument', nargs=1, required=False)
# @click.option('--paths-to-mutate', type=click.STRING)
# @click.option('--backup/--no-backup', default=False)
# @click.option('--use-coverage', is_flag=True, default=False)
# @click.option('--tests-dir')
# @click.option('-s', help='turn off output capture', is_flag=True)
# @click.option('--dict-synonyms')
# @click.option('--cache-only', is_flag=True, default=False)
# @config_from_setup_cfg(
#     dict_synonyms='',
#     runner='python -m pytest -x',
#     tests_dir=DEFAULT_TESTS_DIR,
# )
def main():
    """main entrypoint for mutmut
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
    parser = get_argparser()
    args = parser.parse_args()
    dict_synonyms = [x.strip() for x in "".split(',')]
    runner = 'python -m pytest -x'
    if args.use_coverage and not exists('.coverage'):
        raise FileExistsError(
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
        swallow_output=not args.output_capture,
        test_command=runner,
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

    print('2. Checking mutants')
    config = Config(
        swallow_output=not args.output_capture,
        test_command=runner,
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

    run_mutation_tests(config=config, mutations_by_file=mutations_by_file)


def popen_streaming_output(cmd, callback, timeout=None):
    master, slave = os.openpty()

    p = Popen(
        cmd,
        shell=True,
        stdout=slave,
        stderr=slave,
    )
    stdout = os.fdopen(master)
    os.close(slave)

    start = datetime.now()

    foo = {'raise': False}

    def timeout_killer():
        while p.returncode is None:
            sleep(0.1)
            if (datetime.now() - start).total_seconds() > timeout:
                foo['raise'] = True
                p.kill()
                return

    if timeout:
        t = Thread(target=timeout_killer)
        t.daemon = True
        t.start()

    while p.returncode is None:
        try:
            line = stdout.readline()[
                   :-1]  # -1 to remove the newline at the end
            callback(line)
        except OSError:
            # This seems to happen on some platforms, including TravisCI. It seems like
            # it's ok to just let this pass here, you just won't get as nice feedback.
            pass

        p.poll()

    if foo['raise']:
        raise TimeoutError()

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
    context = Context(
        mutate_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        dict_synonyms=config.dict_synonyms,
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


def run_mutation_tests_for_file(config, file_to_mutate, mutations):
    for mutation_id in mutations:
        status = run_mutation(config, file_to_mutate, mutation_id)
        update_mutant_status(file_to_mutate, mutation_id, status,
                             config.hash_of_tests)
        config.progress += 1
        config.print_progress()


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
        config.print_progress()

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
    start_time = datetime.now()

    output = []

    def feedback(line):
        if not swallow_output:
            print(line)
        print('Running...')
        output.append(line)

    returncode = popen_streaming_output(test_command, feedback)

    if returncode == 0 or (using_testmon and returncode == 5):
        baseline_time_elapsed = (datetime.now() - start_time).total_seconds()
    else:
        raise Exception(
            "Tests don't run cleanly without mutations. Test command was: %s\n\nOutput:\n\n%s" % (
                test_command, '\n'.join(output)))

    print(' Done')

    set_cached_test_time(baseline_time_elapsed)

    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms):
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


if __name__ == '__main__':
    sys.exit(main())
