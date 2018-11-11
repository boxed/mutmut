# coding=utf-8

from __future__ import print_function

import itertools
import os
import sys
from datetime import datetime
from functools import wraps
from io import open
from itertools import groupby
from os.path import isdir, exists
from shutil import move, copy
from subprocess import TimeoutExpired, Popen

import click
from glob2 import glob

from mutmut.cache import write_surviving_mutant, write_timed_out_mutant, write_suspicious_mutant
from . import parse_mutation_id_str, get_mutation_id_str, mutate_file, Context, list_mutations, __version__
from .cache import hash_of, hash_of_tests, update_hash_of_source_file, load_hash_of_source_file, write_tests_hash, load_hash_of_tests, load_surviving_mutants, load_ok_lines, write_ok_line

spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')

if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    # noinspection PyCompatibility,PyUnresolvedReferences
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError
    # This little hack is needed to get the click tester working on python 2.7
    orig_print = print

    def print(x='', **kwargs):
        orig_print(x.encode('utf8'), **kwargs)

else:
    # noinspection PyUnresolvedReferences,PyCompatibility
    from configparser import ConfigParser, NoOptionError, NoSectionError


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
    """
    Manage the printing and in-place updating of a line of characters.
    Note that if the string is longer than a line, then in-place
    updating may not work (it will print a new line at each refresh).
    """
    last_len = [0]

    def p(s):
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        if sys.version_info < (3, 0):  # pragma: no cover (python 2 specific)
            output = output.encode('utf8')
        sys.stdout.write(output)
        sys.stdout.flush()
        last_len[0] = len_s
    return p


print_status = status_printer()


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
            raise ErrorMessage('Could not figure out where the code to mutate is. Please specify it on the command line like "mutmut code_dir" or by adding "paths_to_mutate=code_dir" in setup.cfg under the section [mutmut]')
    else:
        return paths_to_mutate


def do_apply(mutation_id, paths_to_mutate, dict_synonyms, backup):
    assert len(paths_to_mutate) == 1
    context = Context(
        mutate_id=mutation_id,
        filename=paths_to_mutate[0],
        dict_synonyms=dict_synonyms,
    )
    mutate_file(
        backup=backup,
        context=context,
    )
    if context.number_of_performed_mutations == 0:
        raise ErrorMessage('ERROR: no mutations performed. Are you sure the index is not too big?')


class ErrorMessage(Exception):
    pass


null_out = open(os.devnull, 'w')


class Config(object):
    def __init__(self, swallow_output, test_command, exclude_callback, baseline_time_elapsed, backup, dict_synonyms, total, using_testmon, cache_only, tests_dirs):
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
        self.killed_mutants = 0
        self.surviving_mutants = 0
        self.surviving_mutants_timeout = 0
        self.suspicious_mutants = 0

    def print_progress(self):
        print_status('%s/%s  🎉 %s  ⏰ %s  🙁 %s  🤔 %s' % (self.progress, self.total, self.killed_mutants, self.surviving_mutants_timeout, self.surviving_mutants, self.suspicious_mutants))


DEFAULT_TESTS_DIR = '**/tests/:**/test/'


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('paths_to_mutate', nargs=-1)
@click.option('--apply', help='apply the mutation to the given file. Must be used in combination with --mutation_number', is_flag=True)
@click.option('--backup/--no-backup', default=False)
@click.option('--mutation', type=click.STRING)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--tests-dir')
@click.option('-s', help='turn off output capture', is_flag=True)
@click.option('--dict-synonyms')
@click.option('--cache-only', is_flag=True, default=False)
@click.option('--print-results', is_flag=True, default=False)
@click.option('--version', is_flag=True, default=False)
@config_from_setup_cfg(
    dict_synonyms='',
    runner='python -m pytest -x',
    tests_dir=DEFAULT_TESTS_DIR,
)
def main(paths_to_mutate, apply, mutation, backup, runner, tests_dir, s, use_coverage, dict_synonyms, cache_only, print_results, version):

    if version:
        print("mutmut version %s" % __version__)
        return

    if use_coverage and not exists('.coverage'):
        print('No .coverage file found. You must generate a coverage file to use this feature.')
        return

    paths_to_mutate = get_or_guess_paths_to_mutate(paths_to_mutate)

    tests_dirs = []
    for p in tests_dir.split(':'):
        tests_dirs.extend(glob(p, recursive=True))
    del tests_dir

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise ErrorMessage('You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')

    if print_results:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs):
                for surviving_mutant in load_surviving_mutants(filename):
                    print('%s' % get_apply_line(filename, surviving_mutant))
        return 0

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    mutation_id = None
    if mutation:
        if len(paths_to_mutate) > 1 or len(list(python_source_files(paths_to_mutate[0], tests_dirs))) > 1:
            print('When supplying a mutation ID you must only specify one filename')
            exit(1)

        mutation_id = parse_mutation_id_str(mutation)

    del mutation

    if apply:
        do_apply(mutation_id, paths_to_mutate, dict_synonyms, backup)
        return

    try:
        os.mkdir('.mutmut-cache')
    except OSError:
        pass

    using_testmon = '--testmon' in runner

    print("""
- Mutation testing starting - 

These are the steps:
1. A full test suite run will be made to make sure we 
   can run the tests successfully and we know how long 
   it takes (to detect infinite loops for example)
2. Mutants will be generated and checked

Mutants are written to the cache in the .mutmut-cache 
directory. Print found mutants with `mutmut --print-result`.

Legend for output:
🎉 Killed mutants. The goal is for everything to end up in this bucket. 
⏰ Timeout. Test suite took 10 times as long as the baseline so were killed.  
🙁 Survived. This means your tests needs to be expanded. 
🤔 Suspicious. Tests took a long time, but not long enough to be fatal. 
""")

    baseline_time_elapsed = time_test_suite(swallow_output=not s, test_command=runner, using_testmon=using_testmon)

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    coverage_data = read_coverage_data(use_coverage)

    mutations_by_file = {}

    def _exclude(context):
        return coverage_exclude_callback(context=context, use_coverage=use_coverage, coverage_data=coverage_data)

    if mutation_id is None:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs):
                add_mutations_by_file(mutations_by_file, filename, _exclude, dict_synonyms)
    else:
        for path in paths_to_mutate:
            for filename in python_source_files(path, tests_dirs):
                mutations_by_file[filename] = [mutation_id]

    total = sum(len(mutations) for mutations in mutations_by_file.values())

    print()
    print('2. Checking mutants')
    config = Config(
        swallow_output=not s,
        test_command=runner,
        exclude_callback=_exclude,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=backup,
        dict_synonyms=dict_synonyms,
        total=total,
        using_testmon=using_testmon,
        cache_only=cache_only,
        tests_dirs=tests_dirs,
    )

    run_mutation_tests(config=config, mutations_by_file=mutations_by_file)


def popen_streaming_output(cmd, callback):
    master, slave = os.openpty()

    p = Popen(
        cmd,
        shell=True,
        stdout=slave,
        stderr=slave,
    )
    stdout = os.fdopen(master)
    os.close(slave)
    while p.returncode is None:
        line = stdout.readline()[:-1]  # -1 to remove the newline at the end
        callback(line)

        p.poll()

    return p.returncode


def tests_pass(config):
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    kwargs = {}
    if sys.version_info >= (3, 3):
        kwargs['timeout'] = config.baseline_time_elapsed.total_seconds() * 10

    def feedback(line):
        if not config.swallow_output:
            print(line)
        config.print_progress()

    returncode = popen_streaming_output(config.test_command, feedback)
    return returncode == 0 or (config.using_testmon and returncode == 5)


SURVIVING_MUTANT = 'surviving_mutant'
OK = 'ok'


def run_mutation(config, filename, mutation_id):
    context = Context(
        mutate_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        dict_synonyms=config.dict_synonyms,
        config=config,
    )
    try:
        number_of_mutations_performed = mutate_file(
            backup=True,
            context=context
        )
        assert number_of_mutations_performed
        start = datetime.now()
        try:
            survived = tests_pass(config)
        except TimeoutExpired:
            write_timed_out_mutant(filename, mutation_id)
            context.config.surviving_mutants_timeout += 1
            return SURVIVING_MUTANT

        time_elapsed = datetime.now() - start
        if time_elapsed > config.baseline_time_elapsed * 2:
            write_suspicious_mutant(filename, mutation_id)
            config.suspicious_mutants += 1
            return OK

        if survived:
            write_surviving_mutant(filename, mutation_id)
            context.config.surviving_mutants += 1
            return SURVIVING_MUTANT
        else:
            context.config.killed_mutants += 1
            return OK
    finally:
        move(filename + '.bak', filename)


def get_apply_line(filename, mutation_id):
    apply_line = 'mutmut %s --apply --mutation "%s"' % (filename, get_mutation_id_str(mutation_id))
    return apply_line


def changed_file(config, file_to_mutate, mutations):
    old_surviving_mutants = load_surviving_mutants(file_to_mutate)
    old_ok_lines = load_ok_lines(file_to_mutate)

    for line, mutations in groupby(mutations, key=lambda x: x[0]):
        line_state = OK
        if line in old_surviving_mutants or line in old_ok_lines:
            # report set of surviving mutants for line
            config.progress += len(str(mutations))
            config.print_progress()
        else:
            # run mutation tests on line
            for mutation in mutations:
                config.progress += 1
                config.print_progress()
                result = run_mutation(config, file_to_mutate, mutation)
                if result == SURVIVING_MUTANT:
                    line_state = SURVIVING_MUTANT
        if line_state is OK:
            write_ok_line(file_to_mutate, line)


def fail_on_cache_only(config):
    if config.cache_only:
        print_status('')
        print('\rFAILED: changes detected in cache only mode')
        exit(2)


def run_mutation_tests(config, mutations_by_file):
    """
    :type config: Config
    :type mutations_by_file: dict[str, list[tuple]]
    """
    old_hash_of_tests = load_hash_of_tests()
    old_hashes_of_source_files = load_hash_of_source_file()
    new_hashes_of_source_files = {}

    new_hash_of_tests = hash_of_tests(config.tests_dirs)
    # TODO: it's wrong to write this here.. need to write down the proper order of updating the cache
    if not config.cache_only:
        write_tests_hash(new_hash_of_tests)

    if new_hash_of_tests == old_hash_of_tests:
        print('\rUnchanged tests, using cache')

    for file_to_mutate, mutations in mutations_by_file.items():
        old_hash = old_hashes_of_source_files.get(file_to_mutate)
        new_hash = hash_of(file_to_mutate)
        config.print_progress()
        if new_hash_of_tests == old_hash_of_tests:
            if new_hash != old_hash:
                fail_on_cache_only(config)

                changed_file(config, file_to_mutate, mutations)

        else:
            fail_on_cache_only(config)

            # tests have changed
            if new_hash == old_hash:
                changed_file(config, file_to_mutate, load_surviving_mutants(file_to_mutate))
            else:
                changed_file(config, file_to_mutate, mutations)
        update_hash_of_source_file(file_to_mutate, new_hash, new_hashes_of_source_files)


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
    print('1. Running tests without mutations')
    start_time = datetime.now()

    def feedback(line):
        if not swallow_output:
            print(line)
        print_status('Running...')

    returncode = popen_streaming_output(test_command, feedback)

    if returncode == 0 or (using_testmon and returncode == 5):
        baseline_time_elapsed = datetime.now() - start_time
    else:
        raise ErrorMessage("Tests don't run cleanly without mutations. Test command was: %s" % test_command)

    print(' Done')

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
    except Exception:
        print('Failed while creating mutations for %s, for line "%s"' % (context.filename, context.current_source_line))
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
            dirs[:] = [d for d in dirs if os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


if __name__ == '__main__':
    try:
        main()
    except ErrorMessage as main_error:
        print(str(main_error))
