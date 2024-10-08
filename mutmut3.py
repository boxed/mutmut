import ast
import fnmatch
import gc
import itertools
import json
import os
import shutil
import sys
from collections import defaultdict
from configparser import (
    ConfigParser,
    NoOptionError,
    NoSectionError,
)
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
)
from difflib import unified_diff
from functools import lru_cache
from io import TextIOBase
from json import JSONDecodeError
from os import (
    makedirs,
    walk,
)
from os.path import isdir
from pathlib import Path
from typing import (
    Dict,
    List,
)

import click
from parso import parse

import mutmut

# TODO: hash of test functions that invalidates stats collection and results for these
# TODO: collect tests always: first run we collect to update the known list of tests, then we run pytest with that list for stats
#           - when we run again, we ask for all tests, check which are new and which are gone and update by running stats collection for just these
# TODO: when should surviving mutants be retested?
# TODO: pragma no mutate should end up in `skipped` category
# TODO: hash of function. If hash changes, retest all mutants as mutant IDs are not stable
# TODO: exclude mutating static typing


mutmut._stats = set()


status_by_exit_code = {
    1: 'killed',
    3: 'killed',  # internal error in pytest means a kill
    0: 'survived',
    5: 'no tests executed by test runner',
    2: 'check was interrupted by user',
    None: 'not checked',
    33: 'no tests',
    34: 'skipped',
    35: 'suspicious',
    36: 'timeout',
}

emoji_by_status = {
    'survived': '🙁',
    'no tests': '🫥',
    'no tests executed by test runner': '🫥',
    'timeout': '⏰',
    'suspicious': '🤔',
    'skipped': '🔇',
    'check was interrupted by user': '🛑',
    'not checked': '?',
    'killed': '🎉',
}

exit_code_to_emoji = {
    exit_code: emoji_by_status[status]
    for exit_code, status in status_by_exit_code.items()
}


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


def record_trampoline_hit(name):
    mutmut._stats.add(name)


def walk_all_files():
    paths = [guess_paths_to_mutate()]
    for path in paths:
        for root, dirs, files in walk(path):
            for filename in files:
                yield root, filename


def walk_source_files():
    for root, filename in walk_all_files():
        if filename.endswith('.py'):
            yield Path(root) / filename


class InvalidMutantException(Exception):
    pass


class MutmutProgrammaticFailException(Exception):
    pass


# language=python
trampoline_impl = """
from inspect import signature as __signature

def __mutmut_trampoline(orig, mutants, *args, **kwargs):
    import os
    mutant_under_test = os.environ['MUTANT_UNDER_TEST']
    if mutant_under_test == 'fail':
        from __main__ import MutmutProgrammaticFailException
        raise MutmutProgrammaticFailException('Failed programmatically')      
    elif mutant_under_test == 'stats':
        from __main__ import record_trampoline_hit
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__)
        return orig(*args, **kwargs)
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_'
    if not mutant_under_test.startswith(prefix):
        return orig(*args, **kwargs)
    mutant_name = mutant_under_test.rpartition('.')[-1]
    return mutants[mutant_name](*args, **kwargs)

"""


def create_mutants(config: 'Config'):
    for path in walk_source_files():
        output_path = Path('mutants') / path
        makedirs(output_path.parent, exist_ok=True)

        if config.should_ignore_for_mutation(path):
            shutil.copy(path, output_path)
        else:
            create_mutants_for_file(path, output_path)


def copy_also_copy_files(config: 'Config'):
    assert isinstance(config.also_copy, list)
    for path in config.also_copy:
        path = Path(path)
        destination = Path('mutants') / path
        if not path.exists():
            continue
        if path.is_file():
            shutil.copy(path, destination)
        else:
            shutil.copytree(path, destination, dirs_exist_ok=True)


def pragma_no_mutate_lines(source):
    return {
        i + 1
        for i, line in enumerate(source.split('\n'))
        if '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[-1]
    }


def create_mutants_for_file(filename, output_path):
    input_stat = os.stat(filename)

    if output_path.exists() and output_path.stat().st_mtime == input_stat.st_mtime:
        # print('    skipped', output_path, 'already up to date')
        return

    mutant_names = []

    with open(filename) as f:
        source = f.read()

    no_mutate_lines = pragma_no_mutate_lines(source)

    with open(output_path, 'w') as out:
        for x, mutant_name in yield_mutants_for_module(parse(source), no_mutate_lines):
            out.write('\n\n')
            out.write(x)
            if mutant_name:
                mutant_names.append(mutant_name)

    # validate no syntax errors of mutants
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            print(output_path, 'has invalid syntax: ', e)
            exit(1)

    meta_filename = str(output_path) + '.meta'
    with open(meta_filename, 'w') as f:
        module_name = str(filename)[:-len(filename.suffix)].replace(os.sep, '.')
        json.dump(dict(
            result_by_key={
                 '.'.join([module_name, x]).replace('.__init__.', '.'): None
                for x in mutant_names
            },
        ), f, indent=4)

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))


def build_trampoline(orig_name, mutants):
    mutants_dict = f'{orig_name}__mutmut_mutants = {{\n' + ', \n    '.join(f'{repr(m)}: {m}' for m in mutants) + '\n}'

    return f"""
{mutants_dict}

def {orig_name}(*args, **kwargs):
    return __mutmut_trampoline({orig_name}__mutmut_orig, {orig_name}__mutmut_mutants, *args, **kwargs) 

{orig_name}.__signature__ = __signature({orig_name}__mutmut_orig)
{orig_name}__mutmut_orig.__name__ = '{orig_name}'
"""


@contextmanager
def rename(node, *, suffix):
    orig_name = node.name.value
    node.name.value += f'__mutmut_{suffix}'
    yield
    node.name.value = orig_name


def yield_mutants_for_node(*, func_node, context, node):
    return_annotation_started = False

    if hasattr(node, 'children'):
        for child_node in node.children:
            if child_node.type == 'operator' and child_node.value == '->':
                return_annotation_started = True

            if return_annotation_started and child_node.type == 'operator' and child_node.value == ':':
                return_annotation_started = False

            if return_annotation_started:
                continue

            context.stack.append(child_node)
            try:
                yield from yield_mutants_for_node(func_node=func_node, context=context, node=child_node)
            finally:
                context.stack.pop()

    mutation = mutmut.mutations_by_type.get(node.type)
    if not mutation:
        return

    for key, value in sorted(mutation.items()):
        old = getattr(node, key)
        if context.exclude_node(node):
            continue

        new = value(
            context=context,
            node=node,
            value=getattr(node, 'value', None),
            children=getattr(node, 'children', None),
        )

        if isinstance(new, list) and not isinstance(old, list):
            # multiple mutations
            new_list = new
        else:
            # one mutation
            new_list = [new]

        # go through the alternate mutations in reverse as they may have
        # adverse effects on subsequent mutations, this ensures the last
        # mutation applied is the original/default/legacy mutmut mutation
        for new in reversed(new_list):
            assert not callable(new)
            if new is not None and new != old:
                # TODO
                # if hasattr(mutmut_config, 'pre_mutation_ast'):
                #     mutmut_config.pre_mutation_ast(context=context)

                setattr(node, key, new)

                context.count += 1

                # noinspection PyArgumentList
                with rename(func_node, suffix=f'{context.count}'):
                    code = func_node.get_code()

                    try:
                        ast.parse(code)
                        context.mutants.append(func_node.name.value)
                        yield code, func_node.name.value
                    except (SyntaxError, IndentationError):
                        pass

                setattr(node, key, old)


class FuncContext:
    def __init__(self, no_mutate_lines=None):
        self.count = 0
        self.mutants = []
        self.stack = []
        self.dict_synonyms = {}
        self.no_mutate_lines = no_mutate_lines or []

    def exclude_node(self, node):
        if node.start_pos[0] in self.no_mutate_lines:
            return True
        return False


def yield_mutants_for_function(node, *, no_mutate_lines):
    assert node.type == 'funcdef'

    # noinspection PyArgumentList
    with rename(node, suffix='orig'):
        yield node.get_code(), None

    context = FuncContext(no_mutate_lines=no_mutate_lines)

    for child_node in node.children:
        context.stack.append(child_node)
        try:
            yield from yield_mutants_for_node(func_node=node, node=child_node, context=context)
        finally:
            context.stack.pop()

    yield build_trampoline(node.name.value, context.mutants), None


def yield_mutants_for_class(node, no_mutate_lines):
    assert node.type == 'classdef'
    yield node.get_code(), None


def yield_mutants_for_module(node, no_mutate_lines):
    yield trampoline_impl, None
    yield '\n', None
    assert node.type == 'file_input'
    for child_node in node.children:
        # TODO: support methods
        if child_node.type == 'funcdef':
            yield from yield_mutants_for_function(child_node, no_mutate_lines=no_mutate_lines)
        elif child_node.type == 'classdef':
            yield from yield_mutants_for_class(child_node, no_mutate_lines=no_mutate_lines)
        else:
            yield child_node.get_code(), None


class MutationData:
    def __init__(self, *, path):
        self.path = path
        self.meta_path = Path('mutants') / (str(path) + '.meta')
        with open(self.meta_path) as f:
            self.meta = json.load(f)

        self.key_by_pid = {}
        self.result_by_key = self.meta.pop('result_by_key')
        assert not self.meta, self.meta  # We should read all the data!

    def register_pid(self, *, pid, key):
        self.key_by_pid[pid] = key

    def register_result(self, *, pid, exit_code):
        assert self.key_by_pid[pid] in self.result_by_key
        self.result_by_key[self.key_by_pid[pid]] = (0xFF00 & exit_code) >> 8  # The high byte contains the exit code
        # TODO: maybe rate limit this? Saving on each result can slow down mutation testing a lot if the test run is fast.
        self.save()

    def save(self):
        with open(self.meta_path, 'w') as f:
            json.dump(dict(
                result_by_key=self.result_by_key,
            ), f, indent=4)


def unused(*_):
    pass


def strip_prefix(s, *, prefix, strict=False):
    if s.startswith(prefix):
        return s[len(prefix):]
    assert strict is False, f"String '{s}' does not start with prefix '{prefix}'"
    return s


class TestRunner:
    def run_stats(self):
        raise NotImplementedError()

    def run_forced_fail(self):
        raise NotImplementedError()

    def prepare_main_test_run(self):
        pass

    def run_tests(self, *, key, tests):
        raise NotImplementedError()


@contextmanager
def change_cwd(path):
    old_cwd = os.path.abspath(os.getcwd())
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


# For pytest. This function gets installed by pytest's plugin system
def pytest_runtest_teardown(item, nextitem):
    unused(nextitem)
    for function in mutmut._stats:
        mutmut.tests_by_function[function].add(strip_prefix(item._nodeid, prefix='mutants/'))
    mutmut._stats.clear()


class PytestRunner(TestRunner):
    def run_stats(self):
        import pytest
        with change_cwd('mutants'):
            # "-p mutmut3" is used to load this module as a pytest plugin, so we get pytest_runtest_teardown called
            return int(pytest.main(['-p', 'mutmut3', '-x', '-q', '--import-mode=append']))

    def run_tests(self, *, key, tests):
        import pytest
        with change_cwd('mutants'):
            return int(pytest.main(['-x', '-q', '--import-mode=append'] + list(tests)))

    def run_forced_fail(self):
        import pytest
        with change_cwd('mutants'):
            return int(pytest.main(['-x', '-q', '--import-mode=append']))


class HammettRunner(TestRunner):
    def __init__(self):
        self.hammett_kwargs = None

    def run_stats(self):
        import hammett
        print('running hammett stats...')

        def post_test_callback(_name, **_):
            for function in mutmut._stats:
                mutmut.tests_by_function[function].add(_name)
            mutmut._stats.clear()

        return hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, post_test_callback=post_test_callback, use_cache=False, insert_cwd=False)

    def run_forced_fail(self):
        import hammett
        return hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, use_cache=False, insert_cwd=False)

    def prepare_main_test_run(self):
        import hammett
        self.hammett_kwargs = hammett.main_setup(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
            insert_cwd=False,
        )

    def run_tests(self, *, key, tests):
        import hammett
        hammett.Config.workerinput = dict(workerinput=f'_{key}')
        return hammett.main_run_tests(**self.hammett_kwargs, tests=tests)


def orig_function_name_from_key(key):
    return key.partition('__mutmut_')[0]


spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')


def status_printer():
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]
    last_update = [datetime(1900, 1, 1)]
    update_threshold = timedelta(seconds=0.1)

    def p(s, *, force_output=False):
        if not force_output and (datetime.now() - last_update[0]) < update_threshold:
            return
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        sys.__stdout__.write(output)
        sys.__stdout__.flush()
        last_len[0] = len_s
    return p


print_status = status_printer()


@dataclass
class Stat:
    not_checked: int
    killed: int
    survived: int
    total: int
    no_tests: int
    skipped: int
    suspicious: int
    timeout: int
    no_tests_executed_by_test_runner: int
    check_was_interrupted_by_user: int


def collect_stat(m: MutationData):
    r = {
        k.replace(' ', '_'): 0
        for k in status_by_exit_code.values()
    }
    for k, v in m.result_by_key.items():
        r[status_by_exit_code[v].replace(' ', '_')] += 1
    return Stat(
        **r,
        total=sum(r.values()),
    )


def collect_stats(mutation_data_by_path):
    stats = [collect_stat(x) for x in mutation_data_by_path.values()]
    return Stat(
        not_checked=sum(x.not_checked for x in stats),
        killed=sum(x.killed for x in stats),
        survived=sum(x.survived for x in stats),
        total=sum(x.total for x in stats),
        no_tests=sum(x.no_tests for x in stats),
        skipped=sum(x.skipped for x in stats),
        suspicious=sum(x.suspicious for x in stats),
        timeout=sum(x.timeout for x in stats),
        no_tests_executed_by_test_runner=sum(x.no_tests_executed_by_test_runner for x in stats),
        check_was_interrupted_by_user=sum(x.check_was_interrupted_by_user for x in stats),
    )


def print_stats(mutation_data_by_path, force_output=False):
    s = collect_stats(mutation_data_by_path)
    print_status(f'{(s.total - s.not_checked)}/{s.total}  🎉 {s.killed} 🫥 {s.no_tests}  ⏰ {s.timeout}  🤔 {s.suspicious}  🙁 {s.survived}  🔇 {s.skipped}', force_output=force_output)


def run_forced_fail(runner):
    print('running forced fail test')
    os.environ['MUTANT_UNDER_TEST'] = 'fail'
    with CatchOutput() as catcher:
        try:
            if runner.run_forced_fail() == 0:
                catcher.stop()
                print('\n'.join(catcher.strings))
                print("FAILED")
                os._exit(1)
        except MutmutProgrammaticFailException:
            pass
    os.environ['MUTANT_UNDER_TEST'] = ''
    print('    done')


class CatchOutput:
    def __init__(self, callback=lambda s: None):
        self.strings = []

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher):
                self.catcher = catcher

            def write(self, s):
                callback(s)
                self.catcher.strings.append(s)
                return len(s)
        self.redirect = StdOutRedirect(self)

    def stop(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self):
        sys.stdout = self.redirect
        sys.stderr = self.redirect

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@dataclass
class Config:
    also_copy: List[Path]
    do_not_mutate: List[str]

    def should_ignore_for_mutation(self, path):
        if not str(path).endswith('.py'):
            return True
        for p in self.do_not_mutate:
            if fnmatch.fnmatch(path, p):
                return True
        return False


@lru_cache()
def read_config():
    config_parser = ConfigParser()
    config_parser.read('setup.cfg')

    def s(key, default):
        try:
            return config_parser.get('mutmut', key)
        except (NoOptionError, NoSectionError):
            return default

    return Config(
        do_not_mutate=[
            x
            for x in s('do_not_mutate', '').split('\n')
            if x
        ],
        also_copy=[
            Path(y)
            for y in [
                x
                for x in s('also_copy', '').split('\n')
                if x
            ]
        ]+[
            Path('tests/'),
            Path('test/'),
            Path('tests.py'),
        ],
    )


@click.group()
def cli():
    pass


@cli.command()
@click.option('--max-children', type=int)
@click.argument('mutant_names', required=False, nargs=-1)
def run(mutant_names, *, max_children):
    if mutant_names:
        assert isinstance(mutant_names, (tuple, list)), mutant_names

    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!

    start = datetime.now()
    print('generating mutants...')
    config = read_config()
    create_mutants(config)
    copy_also_copy_files(config)
    time = datetime.now() - start
    print(f'    done in {round(time.total_seconds()*1000)}ms', )

    sys.path.insert(0, os.path.abspath('mutants'))

    # TODO: config/option for runner
    # runner = HammettRunner()
    runner = PytestRunner()
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test
    try:
        with open('mutants/mutmut-stats.json') as f:
            mutmut.tests_by_function = {k: set(v) for k, v in json.load(f).items()}
    except (FileNotFoundError, JSONDecodeError):
        mutmut.tests_by_function = None

    if mutmut.tests_by_function is None:
        print('running stats...')
        os.environ['MUTANT_UNDER_TEST'] = 'stats'
        os.environ['PY_IGNORE_IMPORTMISMATCH'] = '1'
        mutmut.tests_by_function = defaultdict(set)
        # with CatchOutput() as output_catcher:

        collect_stats_exit_code = runner.run_stats()
        if collect_stats_exit_code != 0:
            # output_catcher.stop()
            # for l in output_catcher.strings:
            #     print(l, end='')

            print(f'failed to collect stats. runner returned {collect_stats_exit_code}')
            return

        print('    done')

        if not mutmut.tests_by_function:
            print('failed to collect stats, no active tests found')
            return

        with open('mutants/mutmut-stats.json', 'w') as f:
            json.dump({k: list(v) for k, v in mutmut.tests_by_function.items()}, f, indent=4)

    print('running clean tests')
    os.environ['MUTANT_UNDER_TEST'] = ''
    with CatchOutput() as output_catcher:
        clean_test_exit_code = runner.run_tests(key=None, tests=[])
        if clean_test_exit_code != 0:
            output_catcher.stop()
            print(''.join(output_catcher.strings))
            print('failed to run clean test')
            return
    print('    done')

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    run_forced_fail(runner)

    runner.prepare_main_test_run()

    def read_one_child_exit_status():
        pid, exit_code = os.wait()
        mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    mutation_data_by_path: Dict[str, MutationData] = {}
    mutation_data_by_pid: Dict[int, MutationData] = {}  # many pids map to one MutationData
    running_children = 0
    if max_children is None:
        max_children = os.cpu_count() or 4

    start = datetime.now()

    count_tried = 0

    for path in walk_source_files():
        if config.should_ignore_for_mutation(path):
            continue
        assert path not in mutation_data_by_path
        m = MutationData(path=path)
        mutation_data_by_path[str(path)] = m

    mutants = [
        (m, key, result)
        for path, m in mutation_data_by_path.items()
        for key, result in m.result_by_key.items()
    ]

    if mutant_names:
        mutants = [
            (m, key, result)
            for m, key, result in mutants
            if key in mutant_names
        ]

    gc.freeze()

    try:
        print('Running mutation testing...')

        for m, key, result in mutants:
            print_stats(mutation_data_by_path)

            key = key.replace('__init__.', '')
            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and result is not None:
                continue

            # # single threaded:
            # runner.prepare_main_test_run()
            # os.environ['MUTANT_UNDER_TEST'] = key
            # function = function_name_from_key(key)
            # tests = mutmut.tests_by_function[function]
            # result = runner.run_tests(key=key, tests=tests)

            function = orig_function_name_from_key(key)
            tests = mutmut.tests_by_function.get(function, [])

            # print(tests)
            if not tests:
                m.result_by_key[key] = 33
                continue

            pid = os.fork()
            if not pid:
                # In the child
                os.environ['MUTANT_UNDER_TEST'] = key
                function = orig_function_name_from_key(key)

                tests = mutmut.tests_by_function[function]
                if not tests:
                    os._exit(33)

                with CatchOutput():
                    result = runner.run_tests(key=key, tests=tests)

                if result != 0:
                    # TODO: write failure information to stdout?
                    pass
                os._exit(result)
            else:
                # in the parent
                mutation_data_by_pid[pid] = m
                m.register_pid(pid=pid, key=key)
                running_children += 1

            if running_children >= max_children:
                read_one_child_exit_status()
                count_tried += 1
                running_children -= 1

        try:
            while running_children:
                read_one_child_exit_status()
                count_tried += 1
                running_children -= 1
        except ChildProcessError:
            pass
    except KeyboardInterrupt:
        print('aborting...')

    t = datetime.now() - start

    print_stats(mutation_data_by_path, force_output=True)
    print()

    print('mutations/s:', count_tried / t.total_seconds())


@cli.command()
@click.option('--all', default=False)
def results(all):
    for path in walk_source_files():
        if not str(path).endswith('.py'):
            continue
        m = MutationData(path=path)
        print(path)
        for k, v in m.result_by_key.items():
            status = status_by_exit_code[v]
            if status == 'killed' and not all:
                continue
            print(f'    {k}: {status}')


def read_original_ast(path):
    with open(path) as f:
        return parse(f.read())


def read_original_ast_node(path, orig_function_name):
    orig_ast = read_original_ast(path)

    for node in orig_ast.children:
        if node.type == 'funcdef' and node.name.value == orig_function_name:
            return node

    raise FileNotFoundError(f'Could not find original function {orig_function_name}')


def read_mutant_ast_node(path, orig_function_name, mutant_function_name):
    with open(Path('mutants') / path) as f:
        mutants_ast = parse(f.read())

    for node in mutants_ast.children:
        if node.type == 'funcdef' and node.name.value == mutant_function_name:
            node.name.value = orig_function_name
            return node

    raise FileNotFoundError(f'Could not find mutant function {mutant_function_name}')


def find_mutant(config, mutant_name):
    for path in walk_source_files():
        if config.should_ignore_for_mutation(path):
            continue

        m = MutationData(path=path)
        if mutant_name in m.result_by_key:
            return m

    print(f'Could not find mutant {mutant_name}')
    exit(0)


def get_diff_for_mutant(config, mutant_name):
    m = find_mutant(config, mutant_name)
    path = m.path

    print(f'# {mutant_name}: {status_by_exit_code[m.result_by_key[mutant_name]]}')

    orig_function_name = orig_function_name_from_key(mutant_name).rpartition('.')[-1]
    mutant_function_name = mutant_name.rpartition('.')[-1]

    orig_code = read_original_ast_node(path, orig_function_name).get_code().strip()
    mutant_code = read_mutant_ast_node(path, orig_function_name, mutant_function_name).get_code().strip()

    path = str(path)  # difflib requires str, not Path
    return '\n'.join([
        line
        for line in unified_diff(orig_code.split('\n'), mutant_code.split('\n'), fromfile=path, tofile=path, lineterm='')
    ])


@cli.command()
@click.argument('mutant_name')
def show(mutant_name):
    config = read_config()
    print(get_diff_for_mutant(config, mutant_name))
    return


@cli.command()
@click.argument('mutant_name')
def apply(mutant_name):
    try:
        config = read_config()
        apply_mutant(config, mutant_name)
    except FileNotFoundError as e:
        print(e)


def apply_mutant(config, mutant_name):
    m = find_mutant(config, mutant_name)
    path = m.path

    orig_function_name = orig_function_name_from_key(mutant_name).rpartition('.')[-1]
    mutant_function_name = mutant_name.rpartition('.')[-1]
    mutant_ast_node = read_mutant_ast_node(path, orig_function_name, mutant_function_name)

    orig_ast = read_original_ast(path)
    for node in orig_ast.children:
        if node.type == 'funcdef' and node.name.value == orig_function_name:
            node.children = mutant_ast_node.children
            break
    else:
        raise FileNotFoundError(f'Could apply mutant {orig_function_name}')

    with open(path, 'w') as f:
        f.write(orig_ast.get_code())


# TODO: junitxml, html commands

@cli.command()
def browse():
    from textual.app import App
    from textual.containers import Container
    from textual.widgets import Footer
    from textual.widgets import DataTable
    from textual.widgets import TextArea

    class ResultBrowser(App):
        CSS_PATH = "result_browser_layout.tcss"
        BINDINGS = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
        ]

        columns = [
            ('path', 'Path'),
        ] + [
            (status, emoji)
            for status, emoji in emoji_by_status.items()
        ]

        cursor_type = 'row'
        mutation_data_and_stat_by_path = None

        def compose(self):
            with Container(classes='container'):
                yield DataTable(id='files')
                yield DataTable(id='mutants')
            yield TextArea(id='diff_view')
            yield Footer()

        def on_mount(self):
            # files table
            files_table: DataTable = self.query_one('#files')
            files_table.cursor_type = 'row'
            for key, label in self.columns:
                files_table.add_column(key=key, label=label)

            # mutants table
            mutants_table: DataTable = self.query_one('#mutants')
            mutants_table.cursor_type = 'row'
            mutants_table.add_columns('name', 'status')

            self.read_data()
            self.populate_files_table()

        def read_data(self):
            config = read_config()
            self.mutation_data_and_stat_by_path = {}

            for p in walk_source_files():
                if config.should_ignore_for_mutation(p):
                    continue
                mutation_data = MutationData(path=p)
                stat = collect_stat(mutation_data)

                self.mutation_data_and_stat_by_path[p] = mutation_data, stat

        def populate_files_table(self):
            files_table: DataTable = self.query_one('#files')
            files_table.clear()

            for p, (mutation_data, stat) in sorted(self.mutation_data_and_stat_by_path.items()):
                row = [p] + [getattr(stat, k.replace(' ', '_')) for k, _ in self.columns[1:]]
                files_table.add_row(*row, key=p)

        def on_data_table_row_highlighted(self, event):
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == 'files':
                mutants_table: DataTable = self.query_one('#mutants')
                mutants_table.clear()
                mutation_data, stat = self.mutation_data_and_stat_by_path[event.row_key.value]
                for k, v in mutation_data.result_by_key.items():
                    status = status_by_exit_code[v]
                    if status == 'killed':
                        continue
                    mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                assert event.data_table.id == 'mutants'
                diff_view = self.query_one('#diff_view')
                if event.row_key.value is None:
                    diff_view.text = ''
                else:
                    config = read_config()
                    diff_view.text = get_diff_for_mutant(config, event.row_key.value)

        def action_retest_mutant(self):
            mutants_table: DataTable = self.query_one('#mutants')
            if mutants_table.cursor_row is None:
                return

            mutant_name = mutants_table.get_row_at(mutants_table.cursor_row)[0]
            with self.suspend():
                assert sys.argv[-1] == 'browse'
                command = ' '.join([sys.executable] + sys.argv[:-1])
                os.system(f'{command} run {mutant_name}')
                # run([mutants_table.get_row_at(mutants_table.cursor_row)[0]])
                input('press enter to return to browser')

            self.read_data()
            # files_table: DataTable = self.query_one('#files')
            # path = files_table.get_row_at(files_table.cursor_row)[0]

            # status = status_by_exit_code[self.mutation_data_and_stat_by_path[path][0].result_by_key[mutant_name]]
            # mutants_table.update_cell(mutant_name, 'status', emoji_by_status[status])

        def action_apply_mutant(self):
            config = read_config()
            mutants_table: DataTable = self.query_one('#mutants')
            if mutants_table.cursor_row is None:
                return
            apply_mutant(config, mutants_table.get_row_at(mutants_table.cursor_row)[0])

    ResultBrowser().run()


if __name__ == '__main__':
    cli()
