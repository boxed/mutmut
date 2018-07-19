# coding=utf-8

# NOTE: to persistently print to screen, you must first print_status('') and then begin your line with \r

from __future__ import print_function

import hashlib
import os
from itertools import groupby
from subprocess import check_call, CalledProcessError, check_output
import sys
from datetime import datetime
from shutil import move, copy
from os.path import isdir
from functools import wraps
from io import open

import click

from . import mutate_file, Context, list_mutations

if sys.version_info < (3, 0):
    # noinspection PyCompatibility
    from ConfigParser import ConfigParser, NoOptionError, NoSectionError
    # This little hack is needed to get the click tester working on python 2.7
    orig_print = print
    print = lambda x, **kwargs: orig_print(x.encode('utf8'), **kwargs)
    text_type = unicode
else:
    # noinspection PyUnresolvedReferences
    from configparser import ConfigParser, NoOptionError, NoSectionError
    text_type = str


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
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        if sys.version_info < (3, 0):
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


mutation_id_separator = u'⤑'


def do_apply(mutation, paths_to_mutate, dict_synonyms, backup):
    assert mutation is not None

    mutation_id = parse_mutation_id_str(mutation)

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


def hash_of(filename):
    with open(filename, 'rb') as f:
        m = hashlib.sha256()
        m.update(f.read())
        return m.hexdigest()


def hash_of_tests(tests_dir):
    m = hashlib.sha256()
    for root, dirs, files in os.walk(tests_dir):
        for filename in files:
            with open(os.path.join(root, filename), 'rb') as f:
                m.update(f.read())
    return m.hexdigest()


def update_hash_of_source_file(filename, hash_of_file, hashes):
    hashes[filename] = hash_of_file
    with open('.mutmut-cache/hashes', 'w') as f:
        f.writelines(u':'.join([k, v]) + '\n' for k, v in hashes.items())


def load_hash_of_source_file():
    try:
        with open('.mutmut-cache/hashes') as f:
            # noinspection PyTypeChecker
            return dict(line.strip().split(':') for line in f.readlines())
    except IOError:
        return {}


def write_tests_hash(tests_hash):
    with open('.mutmut-cache/tests-hash', 'w') as f:
        f.write(text_type(tests_hash))


def load_hash_of_tests():
    try:
        with open('.mutmut-cache/tests-hash') as f:
            return f.read()
    except IOError:
        return None


def parse_mutation_id_str(s):
    m = s.split(mutation_id_separator)
    m[0] = m[0].replace('\\"', '"')
    m[1] = int(m[1])
    assert len(m) == 2
    return tuple(m)


def get_mutation_id_str(mutation_id):
    return '%s%s%s' % (mutation_id[0].replace('"', '\\"'), mutation_id_separator, mutation_id[1])


def surviving_mutants_filename(f):
    return '.mutmut-cache/%s-surviving-mutants' % f.replace(os.sep, '__')


def ok_lines_filename(f):
    return '.mutmut-cache/%s-ok-lines' % f.replace(os.sep, '__')


def load_surviving_mutants(filename):
    try:
        with open(surviving_mutants_filename(filename)) as f:
            lines = f.read().splitlines()
            return [parse_mutation_id_str(x) for x in lines]

    except IOError:
        return {}


def load_ok_lines(filename):
    try:
        with open(ok_lines_filename(filename)) as f:
            return f.read().splitlines()
    except IOError:
        return {}


def write_ok_line(filename, line):
    with open(ok_lines_filename(filename), 'a') as f:
        f.write(line + '\n')


null_out = open(os.devnull, 'w')


class Config(object):
    def __init__(self, swallow_output, test_command, exclude_callback, baseline_time_elapsed, backup, dict_synonyms, total, using_testmon, show_times):
        self.swallow_output = swallow_output
        self.test_command = test_command
        self.exclude_callback = exclude_callback
        self.baseline_time_elapsed = baseline_time_elapsed
        self.backup = backup
        self.dict_synonyms = dict_synonyms
        self.total = total
        self.using_testmon = using_testmon
        self.show_times = show_times
        self.progress = 0
        self.skipped = 0

    def print_progress(self, file_to_mutate, mutation=None):
        print_status('%s out of %s  (%s%s)' % (self.progress, self.total, file_to_mutate, ' ' + get_mutation_id_str(mutation) if mutation else ''))


@click.command()
@click.argument('paths_to_mutate', nargs=-1)
@click.option('--apply', help='apply the mutation to the given file. Must be used in combination with --mutation_number', is_flag=True)
@click.option('--backup/--no-backup', default=False)
@click.option('--mutation', type=click.STRING)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--tests-dir')
@click.option('-s', help='turn off output capture', is_flag=True)
@click.option('--show-times', help='show times for each mutation', is_flag=True)
@click.option('--dict-synonyms')
@config_from_setup_cfg(
    dict_synonyms='',
    runner='python -m pytest -x',
    tests_dir='tests/',
    show_times=False,
)
def main(paths_to_mutate, apply, mutation, backup, runner, tests_dir, s, use_coverage, dict_synonyms, show_times):
    paths_to_mutate = get_or_guess_paths_to_mutate(paths_to_mutate)

    if not isinstance(paths_to_mutate, (list, tuple)):
        paths_to_mutate = [x.strip() for x in paths_to_mutate.split(',')]

    if not paths_to_mutate:
        raise ErrorMessage('You must specify a list of paths to mutate. Either as a command line argument, or by setting paths_to_mutate under the section [mutmut] in setup.cfg')

    dict_synonyms = [x.strip() for x in dict_synonyms.split(',')]

    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    if apply:
        do_apply(mutation, paths_to_mutate, dict_synonyms, backup)
        return

    try:
        os.mkdir('.mutmut-cache')
    except OSError:
        pass

    del mutation

    test_command = '%s %s' % (runner, tests_dir)

    using_testmon = '--testmon' in test_command

    baseline_time_elapsed = time_test_suite(test_command, using_testmon)

    if using_testmon:
        copy('.testmondata', '.testmondata-initial')

    coverage_data = read_coverage_data(use_coverage)

    mutations_by_file = {}

    def _exclude(context):
        return exclude_callback(context=context, use_coverage=use_coverage, coverage_data=coverage_data)

    for path in paths_to_mutate:
        for filename in python_source_files(path):
            add_mutations_by_file(mutations_by_file, filename, _exclude, dict_synonyms)

    total = sum(len(mutations) for mutations in mutations_by_file.values())

    print('--- starting mutation ---')
    config = Config(
        swallow_output=not s,
        test_command=test_command,
        exclude_callback=_exclude,
        baseline_time_elapsed=baseline_time_elapsed,
        backup=backup,
        dict_synonyms=dict_synonyms,
        total=total,
        using_testmon=using_testmon,
        show_times=show_times,
    )

    run_mutation_tests(config=config, mutations_by_file=mutations_by_file, tests_dir=tests_dir)


def tests_pass(config):
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    try:
        check_call(
            config.test_command,
            shell=True,
            stdout=null_out if config.swallow_output else None,
            stderr=null_out if config.swallow_output else None,
        )

        return True
    except CalledProcessError as e:
        return False


def write_surviving_mutant(filename, mutation_id):
    surviving_mutants = load_surviving_mutants(filename)
    if mutation_id in surviving_mutants:
        # Avoid storing the same mutant again
        return

    with open(surviving_mutants_filename(filename), 'a') as f:
        f.write(get_mutation_id_str(mutation_id) + '\n')


SURVIVING_MUTANT = 'surviving_mutant'
OK = 'ok'


def run_mutation(config, filename, mutation_id):
    context = Context(
        mutate_id=mutation_id,
        filename=filename,
        exclude=config.exclude_callback,
        dict_synonyms=config.dict_synonyms,
    )
    try:
        number_of_mutations_performed = mutate_file(
            backup=True,
            context=context
        )
        assert number_of_mutations_performed
        start = datetime.now()
        survived = not tests_pass(config)
        time_elapsed = datetime.now() - start
        if time_elapsed > config.baseline_time_elapsed * 2:
            print('\nSUSPICIOUS LONG TIME: %s > expected %s\n   %s' % (time_elapsed, config.baseline_time_elapsed, get_apply_line(filename, mutation_id)))

        if config.show_times:
            print('time: %s' % time_elapsed)

        if survived:
            print_status('')
            print('\rFAILED: %s' % get_apply_line(filename, mutation_id))
            write_surviving_mutant(filename, mutation_id)
            return SURVIVING_MUTANT
        else:
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
            print_status('')
            print('\rold line')
            config.progress += len(str(mutations))
            config.print_progress(file_to_mutate)
        else:
            # run mutation tests on line
            for mutation in mutations:
                config.progress += 1
                config.print_progress(file_to_mutate, mutation)
                x = run_mutation(config, file_to_mutate, mutation)
                if x == SURVIVING_MUTANT:
                    line_state = SURVIVING_MUTANT
        if line_state is OK:
            write_ok_line(file_to_mutate, line)


def run_mutation_tests(config, mutations_by_file, tests_dir):
    """

    :type config: Config
    """
    old_hash_of_tests = load_hash_of_tests()
    old_hashes_of_source_files = load_hash_of_source_file()
    new_hashes_of_source_files = {}

    new_hash_of_tests = hash_of_tests(tests_dir)
    # TODO: it's wrong to write this here.. need to write down the proper order of updating the cache
    write_tests_hash(new_hash_of_tests)

    for file_to_mutate, mutations in mutations_by_file.items():
        old_hash = old_hashes_of_source_files.get(file_to_mutate)
        new_hash = hash_of(file_to_mutate)
        config.print_progress(file_to_mutate)
        if new_hash_of_tests == old_hash_of_tests:
            if new_hash == old_hash:
                print_status('')
                print('\rUnchanged file %s' % file_to_mutate)
                for surviving_mutant in load_surviving_mutants(file_to_mutate):
                    print('\r(cached existing) FAILED: %s' % get_apply_line(file_to_mutate, surviving_mutant))
            else:
                changed_file(config, file_to_mutate, mutations)

        else:
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


def time_test_suite(test_command, using_testmon):
    print('Running tests without mutations...', end='')
    start_time = datetime.now()
    try:
        check_output(test_command, shell=True)
        baseline_time_elapsed = datetime.now() - start_time
    except CalledProcessError as e:
        if using_testmon and e.returncode == 5:
            baseline_time_elapsed = datetime.now() - start_time
        else:
            raise ErrorMessage("Tests don't run cleanly without mutations. Test command was: %s\n\n%s" % (test_command, e.output.decode()))
    print(' Done')
    return baseline_time_elapsed


def add_mutations_by_file(mutations_by_file, filename, exclude, dict_synonyms):
    mutations_by_file[filename] = list_mutations(
        Context(
            source=open(filename).read(),
            filename=filename,
            exclude=exclude,
            dict_synonyms=dict_synonyms,
        )
    )


def exclude_callback(context, use_coverage, coverage_data):
    if use_coverage:
        measured_lines = coverage_data.lines(os.path.abspath(context.filename))
        if measured_lines is None:
            return True
        if context.current_line not in measured_lines:
            return True

    return False


def python_source_files(path):
    if isdir(path):
        for root, dirs, files in os.walk(path):
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
