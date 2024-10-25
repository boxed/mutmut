import ast
import fnmatch
import gc
import inspect
import itertools
import json
import os
import shutil
import sys
from abc import ABC
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
from hashlib import md5
from io import TextIOBase
from json import JSONDecodeError
from math import ceil
from os import (
    makedirs,
    walk,
)
from os.path import isdir
from pathlib import Path
from signal import SIGTERM
from textwrap import (
    dedent,
    indent,
)
import resource

from threading import Thread
from time import process_time
from typing import (
    Dict,
    List,
)

import click
from parso import (
    parse,
    ParserSyntaxError,
)
from setproctitle import setproctitle

import mutmut


# Document: surviving mutants are retested when you ask mutmut to retest them, interactively in the UI or via command line

# TODO: only count a test for a function if the stack depth to get to the test < some configurable limit.

# TODO: collect tests always: first run we collect to update the known list of tests, then we run pytest with that list for stats
#           - when we run again, we ask for all tests, check which are new and which are gone and update by running stats collection for just these
# TODO: pragma no mutate should end up in `skipped` category
# TODO: hash of function. If hash changes, retest all mutants as mutant IDs are not stable
# TODO: exclude mutating static typing
# TODO: implement timeout

# TODO: don't remove arguments to `isinstance`, as that will always fail. Same with `len`


NEVER_MUTATE_FUNCTION_NAMES = {'__getattribute__', '__setattr__'}
NEVER_MUTATE_FUNCTION_CALLS = {'isinstance', 'len'}
CLASS_NAME_SEPARATOR = 'ǁ'


status_by_exit_code = {
    1: 'killed',
    3: 'killed',  # internal error in pytest means a kill
    0: 'survived',
    5: 'no tests',
    2: 'check was interrupted by user',
    None: 'not checked',
    33: 'no tests',
    34: 'skipped',
    35: 'suspicious',
    36: 'timeout',
    152: 'timeout',  # SIGXCPU
}

emoji_by_status = {
    'survived': '🙁',
    'no tests': '🫥',
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
    if mutmut.config.max_stack_depth != -1:
        f = inspect.currentframe()
        c = mutmut.config.max_stack_depth
        while c and f:
            if 'pytest' in f.f_code.co_filename or 'hammett' in f.f_code.co_filename:
                break
            f = f.f_back
            c -= 1

        if not c:
            return

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


class CollectTestsFailedException(Exception):
    pass


class BadTestExecutionCommandsException(Exception):
    pass

# language=python
trampoline_impl = """
from inspect import signature as _mutmut_signature

def _mutmut_trampoline(orig, mutants, *args, **kwargs):
    import os
    mutant_under_test = os.environ['MUTANT_UNDER_TEST']
    if mutant_under_test == 'fail':
        from mutmut.__main__ import MutmutProgrammaticFailException
        raise MutmutProgrammaticFailException('Failed programmatically')      
    elif mutant_under_test == 'stats':
        from mutmut.__main__ import record_trampoline_hit
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__)
        result = orig(*args, **kwargs)
        return result  # for the yield case
    prefix = orig.__module__ + '.' + orig.__name__ + '__mutmut_'
    if not mutant_under_test.startswith(prefix):
        result = orig(*args, **kwargs)
        return result  # for the yield case
    mutant_name = mutant_under_test.rpartition('.')[-1]
    result = mutants[mutant_name](*args, **kwargs)
    return result

"""
yield_from_trampoline_impl = trampoline_impl.replace('result = ', 'result = yield from ').replace('_mutmut_trampoline', '_mutmut_yield_from_trampoline')


def create_mutants():
    for path in walk_source_files():
        output_path = Path('mutants') / path
        makedirs(output_path.parent, exist_ok=True)

        if mutmut.config.should_ignore_for_mutation(path):
            shutil.copy(path, output_path)
        else:
            create_mutants_for_file(path, output_path)


def copy_also_copy_files():
    assert isinstance(mutmut.config.also_copy, list)
    for path in mutmut.config.also_copy:
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

    with open(filename) as f:
        source = f.read()

    with open(output_path, 'w') as out:
        mutant_names, hash_by_function_name = write_all_mutants_to_file(out=out, source=source, filename=filename)

    # validate no syntax errors of mutants
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            print(output_path, 'has invalid syntax: ', e)
            exit(1)

    source_file_mutation_data = SourceFileMutationData(path=filename)
    module_name = strip_prefix(str(filename)[:-len(filename.suffix)].replace(os.sep, '.'), prefix='src.')

    source_file_mutation_data.exit_code_by_key = {
         '.'.join([module_name, x]).replace('.__init__.', '.'): None
        for x in mutant_names
    }
    source_file_mutation_data.hash_by_function_name = hash_by_function_name
    assert None not in hash_by_function_name
    source_file_mutation_data.save()

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))


def ensure_ends_with_newline(source):
    if not source.endswith('\n'):
        return source + '\n'
    else:
        return source


def write_all_mutants_to_file(*, out, source, filename):
    no_mutate_lines = pragma_no_mutate_lines(source)

    hash_by_function_name = {}
    mutant_names = []

    try:
        ast = parse(ensure_ends_with_newline(source), error_recovery=False)
    except ParserSyntaxError:
        print(f'Warning: unsupported syntax in {filename}, skipping')
        out.write(source)
        return [], {}

    for type_, x, name_and_hash, mutant_name in yield_mutants_for_module(ast, no_mutate_lines):
        out.write(x)
        if mutant_name:
            mutant_names.append(mutant_name)
        if name_and_hash:
            assert type_ == 'orig'
            name, hash = name_and_hash
            hash_by_function_name[name] = hash

    return mutant_names, hash_by_function_name


def build_trampoline(*, orig_name, mutants, class_name, is_generator):
    assert orig_name not in NEVER_MUTATE_FUNCTION_NAMES

    mangled_name = mangle_function_name(name=orig_name, class_name=class_name)

    mutants_dict = f'{mangled_name}__mutmut_mutants = {{\n' + ', \n    '.join(f'{repr(m)}: {m}' for m in mutants) + '\n}'
    access_prefix = ''
    access_suffix = ''
    if class_name is not None:
        access_prefix = f'object.__getattribute__(self, "'
        access_suffix = '")'

    if is_generator:
        yield_statement = 'yield from '  # note the space at the end!
        trampoline_name = '_mutmut_yield_from_trampoline'
    else:
        yield_statement = ''
        trampoline_name = '_mutmut_trampoline'

    return f"""
{mutants_dict}

def {orig_name}({'self, ' if class_name is not None else ''}*args, **kwargs):
    result = {yield_statement}{trampoline_name}({access_prefix}{mangled_name}__mutmut_orig{access_suffix}, {access_prefix}{mangled_name}__mutmut_mutants{access_suffix}, *args, **kwargs)
    return result 

{orig_name}.__signature__ = _mutmut_signature({mangled_name}__mutmut_orig)
{mangled_name}__mutmut_orig.__name__ = '{mangled_name}'
"""


@contextmanager
def rename_function_node(node, *, suffix, class_name):
    orig_name = node.name.value

    mangled_name = mangle_function_name(name=orig_name, class_name=class_name)

    node.name.value = mangled_name + f'__mutmut_{suffix}'
    yield
    node.name.value = orig_name


sentinel = object()


def filter_funcdef_children(children):
    # Throw away type annotation for return type
    r = []
    in_annotation = False
    for c in children:
        if c.type == 'operator':
            if c.value == '->':
                in_annotation = True
            if c.value == ':':
                in_annotation = False

        if not in_annotation:
            r.append(c)
    return r


def yield_mutants_for_node(*, func_node, class_name=None, context, node):
    # do not mutate static typing annotations
    if node.type == 'tfpdef':
        return

    # Some functions should not be mutated
    if node.type == 'atom_expr' and node.children[0].type == 'name' and node.children[0].value in NEVER_MUTATE_FUNCTION_CALLS:
        return

    # The rest
    if hasattr(node, 'children'):
        children = node.children
        if node.type == 'funcdef':
            children = filter_funcdef_children(children)
        for child_node in children:
            context.stack.append(child_node)
            try:
                yield from yield_mutants_for_node(func_node=func_node, class_name=class_name, context=context, node=child_node)
            finally:
                context.stack.pop()

    mutation = mutmut.mutation_by_ast_type.get(node.type)
    if not mutation:
        return

    if context.exclude_node(node):
        return

    old_value = getattr(node, 'value', sentinel)
    old_children = getattr(node, 'children', sentinel)

    for m in mutation(
        context=context,
        node=node,
        value=getattr(node, 'value', None),
        children=getattr(node, 'children', None),
    ):
        new_value = m.get('value', sentinel)
        new_children = m.get('children', sentinel)
        assert new_value is not sentinel or new_children is not sentinel
        if new_value is not sentinel:
            assert old_value != new_value
            setattr(node, 'value', new_value)
        if new_children is not sentinel:
            assert isinstance(new_children, list)
            assert old_children != new_children
            setattr(node, 'children', new_children)

        # noinspection PyArgumentList
        with rename_function_node(func_node, suffix=f'{context.count}', class_name=class_name):
            code = func_node.get_code()
            if valid_syntax(code):
                context.count += 1

                context.mutants.append(func_node.name.value)
                yield 'mutant', code, None, func_node.name.value

            if old_value is not sentinel:
                setattr(node, 'value', old_value)
            if old_children is not sentinel:
                setattr(node, 'children', old_children)


def valid_syntax(code):
    try:
        ast.parse(dedent(code))
        return True
    except (SyntaxError, IndentationError):
        return False


class FuncContext:
    def __init__(self, no_mutate_lines=None, dict_synonyms=None):
        self.count = 1
        self.mutants = []
        self.stack = []
        self.dict_synonyms = {'dict'} | (dict_synonyms or set())
        self.no_mutate_lines = no_mutate_lines or []

    def exclude_node(self, node):
        if node.start_pos[0] in self.no_mutate_lines:
            return True
        return False

    def is_inside_annassign(self):
        for node in self.stack:
            if node.type == 'annassign':
                return True
        return False

    def is_inside_dict_synonym_call(self):
        for node in self.stack:
            if node.type == 'atom_expr' and node.children[0].type == 'name' and node.children[0].value in self.dict_synonyms:
                return True
        return False


def is_generator(node):
    assert node.type == 'funcdef'

    def _is_generator(n):
        if n is not node and n.type in ('funcdef', 'classdef'):
            return False

        if n.type == 'keyword' and n.value == 'yield':
            return True

        for c in getattr(n, 'children', []):
            if _is_generator(c):
                return True
        return False
    return _is_generator(node)


def yield_mutants_for_function(node, *, class_name=None, no_mutate_lines):
    assert node.type == 'funcdef'

    if node.name.value in NEVER_MUTATE_FUNCTION_NAMES:
        yield 'filler', node.get_code(), None, None
        return

    hash_of_orig = md5(node.get_code().encode()).hexdigest()

    orig_name = node.name.value
    # noinspection PyArgumentList
    with rename_function_node(node, suffix='orig', class_name=class_name):
        yield 'orig', node.get_code(), (orig_name, hash_of_orig), None

    context = FuncContext(no_mutate_lines=no_mutate_lines)

    return_annotation_started = False

    for child_node in node.children:
        if child_node.type == 'operator' and child_node.value == '->':
            return_annotation_started = True

        if return_annotation_started and child_node.type == 'operator' and child_node.value == ':':
            return_annotation_started = False

        if return_annotation_started:
            continue

        context.stack.append(child_node)
        try:
            yield from yield_mutants_for_node(func_node=node, class_name=class_name, node=child_node, context=context)
        finally:
            context.stack.pop()

    trampoline = build_trampoline(orig_name=node.name.value, mutants=context.mutants, class_name=class_name, is_generator=is_generator(node))
    if class_name is not None:
        trampoline = indent(trampoline, '    ')
    yield 'trampoline', trampoline, None, None
    yield 'filler', '\n\n', None, None


def yield_mutants_for_class(node, no_mutate_lines):
    assert node.type == 'classdef'
    for child_node in node.children:
        if child_node.type == 'suite':
            yield from yield_mutants_for_class_body(child_node, no_mutate_lines=no_mutate_lines)
        else:
            yield 'filler', child_node.get_code(), None, None


def yield_mutants_for_class_body(node, no_mutate_lines):
    assert node.type == 'suite'
    class_name = node.parent.name.value

    for child_node in node.children:
        if child_node.type == 'funcdef':
            yield from yield_mutants_for_function(child_node, class_name=class_name, no_mutate_lines=no_mutate_lines)
        else:
            yield 'filler', child_node.get_code(), None, None


def is_from_future_import_node(c):
    if c.type == 'simple_stmt':
        if c.children:
            c2 = c.children[0]
            if c2.type == 'import_from' and c2.children[1].type == 'name' and c2.children[1].value == '__future__':
                return True
    return False


def yield_future_imports(node):
    for c in node.children:
        if is_from_future_import_node(c):
            yield 'filler', c.get_code(), None, None


def yield_mutants_for_module(node, no_mutate_lines):
    assert node.type == 'file_input'

    # First yield `from __future__`, then the rest
    yield from yield_future_imports(node)

    yield 'trampoline_impl', trampoline_impl, None, None
    yield 'trampoline_impl', yield_from_trampoline_impl, None, None
    yield 'filler', '\n', None, None
    for child_node in node.children:
        if child_node.type == 'funcdef':
            yield from yield_mutants_for_function(child_node, no_mutate_lines=no_mutate_lines)
        elif child_node.type == 'classdef':
            yield from yield_mutants_for_class(child_node, no_mutate_lines=no_mutate_lines)
        elif is_from_future_import_node(child_node):
            # Don't yield `from __future__` after trampoline
            pass
        else:
            yield 'filler', child_node.get_code(), None, None


class SourceFileMutationData:
    def __init__(self, *, path):
        self.path = path
        self.meta_path = Path('mutants') / (str(path) + '.meta')
        self.meta = None
        self.key_by_pid = {}
        self.exit_code_by_key = {}
        self.hash_by_function_name = {}
        self.start_time_by_pid = {}

    def load(self):
        try:
            with open(self.meta_path) as f:
                self.meta = json.load(f)
        except FileNotFoundError:
            return

        self.exit_code_by_key = self.meta.pop('exit_code_by_key')
        self.hash_by_function_name = self.meta.pop('hash_by_function_name')
        assert not self.meta, self.meta  # We should read all the data!

    def register_pid(self, *, pid, key):
        self.key_by_pid[pid] = key
        self.start_time_by_pid[pid] = datetime.now()

    def register_result(self, *, pid, exit_code):
        assert self.key_by_pid[pid] in self.exit_code_by_key
        self.exit_code_by_key[self.key_by_pid[pid]] = (0xFF00 & exit_code) >> 8  # The high byte contains the exit code
        # TODO: maybe rate limit this? Saving on each result can slow down mutation testing a lot if the test run is fast.
        del self.key_by_pid[pid]
        del self.start_time_by_pid[pid]
        self.save()

    def stop_children(self):
        for pid in self.key_by_pid.keys():
            os.kill(pid, SIGTERM)

    def save(self):
        with open(self.meta_path, 'w') as f:
            json.dump(dict(
                exit_code_by_key=self.exit_code_by_key,
                hash_by_function_name=self.hash_by_function_name,
            ), f, indent=4)


def unused(*_):
    pass


def strip_prefix(s, *, prefix, strict=False):
    if s.startswith(prefix):
        return s[len(prefix):]
    assert strict is False, f"String '{s}' does not start with prefix '{prefix}'"
    return s


class TestRunner(ABC):
    def run_stats(self, *, tests):
        raise NotImplementedError()

    def run_forced_fail(self):
        raise NotImplementedError()

    def prepare_main_test_run(self):
        pass

    def run_tests(self, *, mutant_name, tests):
        raise NotImplementedError()

    def list_all_tests(self):
        raise NotImplementedError()


@contextmanager
def change_cwd(path):
    old_cwd = os.path.abspath(os.getcwd())
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def collected_test_names():
    return {
        test_name
        for _, test_names in mutmut.tests_by_mangled_function_name.items()
        for test_name in test_names
    }


class ListAllTestsResult:
    def __init__(self, *, ids):
        assert isinstance(ids, set)
        self.ids = ids

    def clear_out_obsolete_test_names(self):
        count_before = len(mutmut.tests_by_mangled_function_name)
        mutmut.tests_by_mangled_function_name = {
            k: {test_name for test_name in test_names if test_name in self.ids}
            for k, test_names in mutmut.tests_by_mangled_function_name.items()
        }
        count_after = len(mutmut.tests_by_mangled_function_name)
        if count_before != count_after:
            print(f'Removed {count_before - count_after} obsolete test names')
            save_stats()

    def new_tests(self):
        return self.ids - collected_test_names()


class PytestRunner(TestRunner):
    def execute_pytest(self, params, **kwargs):
        import pytest
        exit_code = int(pytest.main(params, **kwargs))
        if exit_code == 4:
            raise BadTestExecutionCommandsException(params)
        return exit_code

    def run_stats(self, *, tests):
        class StatsCollector:
            def pytest_runtest_teardown(self, item, nextitem):
                unused(nextitem)
                for function in mutmut._stats:
                    mutmut.tests_by_mangled_function_name[function].add(strip_prefix(item._nodeid, prefix='mutants/'))
                mutmut._stats.clear()

            def pytest_runtest_makereport(self, item, call):
                mutmut.duration_by_test[item.nodeid] = call.duration

        stats_collector = StatsCollector()

        with change_cwd('mutants'):
            return int(self.execute_pytest(['-x', '-q', '--import-mode=append'] + list(tests), plugins=[stats_collector]))

    def run_tests(self, *, mutant_name, tests):
        with change_cwd('mutants'):
            return int(self.execute_pytest(['-x', '-q', '--import-mode=append'] + list(tests)))

    def run_forced_fail(self):
        with change_cwd('mutants'):
            return int(self.execute_pytest(['-x', '-q', '--import-mode=append']))

    def list_all_tests(self):
        class TestsCollector:
            def pytest_collection_modifyitems(self, items):
                self.nodeids = {item.nodeid for item in items}

        collector = TestsCollector()

        with change_cwd('mutants'):
            exit_code = int(self.execute_pytest(['-x', '-q', '--collect-only'], plugins=[collector]))
            if exit_code != 0:
                raise CollectTestsFailedException()

        return ListAllTestsResult(ids=collector.nodeids)


class HammettRunner(TestRunner):
    def __init__(self):
        self.hammett_kwargs = None

    def run_stats(self, *, tests):
        import hammett
        print('running hammett stats...')

        def post_test_callback(_name, **_):
            for function in mutmut._stats:
                mutmut.tests_by_mangled_function_name[function].add(_name)
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

    def run_tests(self, *, mutant_name, tests):
        import hammett
        hammett.Config.workerinput = dict(workerinput=f'_{mutant_name}')
        return hammett.main_run_tests(**self.hammett_kwargs, tests=tests)


def mangle_function_name(*, name, class_name):
    assert CLASS_NAME_SEPARATOR not in name
    prefix = ''
    if class_name:
        assert CLASS_NAME_SEPARATOR not in class_name
        prefix = f'x{CLASS_NAME_SEPARATOR}{class_name}{CLASS_NAME_SEPARATOR}'
    else:
        prefix = 'x_'
    return f'{prefix}{name}'


def mangled_name_from_mutant_name(mutant_name):
    assert '__mutmut_' in mutant_name, mutant_name
    return mutant_name.partition('__mutmut_')[0]


def orig_function_and_class_names_from_key(mutant_name):
    r = mangled_name_from_mutant_name(mutant_name)
    _, _, r = r.rpartition('.')
    class_name = None
    if CLASS_NAME_SEPARATOR in r:
        class_name = r[r.index(CLASS_NAME_SEPARATOR) + 1: r.rindex(CLASS_NAME_SEPARATOR)]
        r = r[r.rindex(CLASS_NAME_SEPARATOR) + 1:]
    else:
        assert r.startswith('x_'), r
        r = r[2:]
    return r, class_name


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
    check_was_interrupted_by_user: int


def collect_stat(m: SourceFileMutationData):
    r = {
        k.replace(' ', '_'): 0
        for k in status_by_exit_code.values()
    }
    for k, v in m.exit_code_by_key.items():
        r[status_by_exit_code[v].replace(' ', '_')] += 1
    return Stat(
        **r,
        total=sum(r.values()),
    )


def calculate_summary_stats(source_file_mutation_data_by_path):
    stats = [collect_stat(x) for x in source_file_mutation_data_by_path.values()]
    return Stat(
        not_checked=sum(x.not_checked for x in stats),
        killed=sum(x.killed for x in stats),
        survived=sum(x.survived for x in stats),
        total=sum(x.total for x in stats),
        no_tests=sum(x.no_tests for x in stats),
        skipped=sum(x.skipped for x in stats),
        suspicious=sum(x.suspicious for x in stats),
        timeout=sum(x.timeout for x in stats),
        check_was_interrupted_by_user=sum(x.check_was_interrupted_by_user for x in stats),
    )


def print_stats(source_file_mutation_data_by_path, force_output=False):
    s = calculate_summary_stats(source_file_mutation_data_by_path)
    print_status(f'{(s.total - s.not_checked)}/{s.total}  🎉 {s.killed} 🫥 {s.no_tests}  ⏰ {s.timeout}  🤔 {s.suspicious}  🙁 {s.survived}  🔇 {s.skipped}', force_output=force_output)


def run_forced_fail(runner):
    os.environ['MUTANT_UNDER_TEST'] = 'fail'
    with CatchOutput(show_spinner=True, spinner_title='running forced fail test') as catcher:
        try:
            if runner.run_forced_fail() == 0:
                catcher.dump_output()
                print("FAILED")
                os._exit(1)
        except MutmutProgrammaticFailException:
            pass
    os.environ['MUTANT_UNDER_TEST'] = ''
    print('    done')


class CatchOutput:
    def __init__(self, callback=lambda s: None, show_spinner=False, spinner_title=None):
        self.strings = []
        self.show_spinner = show_spinner
        self.spinner_title = spinner_title or ''

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher):
                self.catcher = catcher

            def write(self, s):
                callback(s)
                if show_spinner:
                    print_status(spinner_title)
                self.catcher.strings.append(s)
                return len(s)
        self.redirect = StdOutRedirect(self)

    def stop(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self):
        if self.show_spinner:
            print_status(self.spinner_title)
        sys.stdout = self.redirect
        sys.stderr = self.redirect

    def dump_output(self):
        self.stop()
        for l in self.strings:
             print(l, end='')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        if self.show_spinner:
            print()


@dataclass
class Config:
    also_copy: List[Path]
    do_not_mutate: List[str]
    max_stack_depth: int

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

    mutmut.config = Config(
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
        max_stack_depth=int(s('max_stack_depth', '-1'))
    )


@click.group()
def cli():
    pass


def run_stats_collection(runner, tests=None):
    if tests is None:
        tests = []  # Meaning all...

    os.environ['MUTANT_UNDER_TEST'] = 'stats'
    os.environ['PY_IGNORE_IMPORTMISMATCH'] = '1'
    start_cpu_time = process_time()

    with CatchOutput(show_spinner=True, spinner_title='running stats') as output_catcher:
        collect_stats_exit_code = runner.run_stats(tests=tests)
        if collect_stats_exit_code != 0:
            output_catcher.dump_output()
            print(f'failed to collect stats. runner returned {collect_stats_exit_code}')
            exit(1)

    print('    done')
    if not tests:  # again, meaning all
        mutmut.stats_time = process_time() - start_cpu_time

    if not collected_test_names():
        print('failed to collect stats, no active tests found')
        exit(1)

    save_stats()


def collect_or_load_stats(runner):
    did_load = load_stats()

    if not did_load:
        # Run full stats
        run_stats_collection(runner)
    else:
        # Run incremental stats
        with CatchOutput(show_spinner=True, spinner_title='collecting stats') as output_catcher:
            os.environ['MUTANT_UNDER_TEST'] = 'list_all_tests'
            try:
                all_tests_result = runner.list_all_tests()
            except CollectTestsFailedException:
                output_catcher.dump_output()
                print('Failed to collect list of tests')
                exit(1)

        all_tests_result.clear_out_obsolete_test_names()

        new_tests = all_tests_result.new_tests()

        if new_tests:
            run_stats_collection(runner, tests=new_tests)


def load_stats():
    did_load = False
    try:
        with open('mutants/mutmut-stats.json') as f:
            data = json.load(f)
            for k, v in data.pop('tests_by_mangled_function_name').items():
                mutmut.tests_by_mangled_function_name[k] |= set(v)
            mutmut.duration_by_test = data.pop('duration_by_test')
            mutmut.stats_time = data.pop('stats_time')
            assert not data, data
            did_load = True
    except (FileNotFoundError, JSONDecodeError):
        pass
    return did_load


def save_stats():
    with open('mutants/mutmut-stats.json', 'w') as f:
        json.dump(dict(
            tests_by_mangled_function_name={k: list(v) for k, v in mutmut.tests_by_mangled_function_name.items()},
            duration_by_test=mutmut.duration_by_test,
            stats_time=mutmut.stats_time,
        ), f, indent=4)


def collect_source_file_mutation_data(*, mutant_names):
    source_file_mutation_data_by_path: Dict[str, SourceFileMutationData] = {}

    for path in walk_source_files():
        if mutmut.config.should_ignore_for_mutation(path):
            continue
        assert path not in source_file_mutation_data_by_path
        m = SourceFileMutationData(path=path)
        m.load()
        source_file_mutation_data_by_path[str(path)] = m

    mutants = [
        (m, mutant_name, result)
        for path, m in source_file_mutation_data_by_path.items()
        for mutant_name, result in m.exit_code_by_key.items()
    ]

    if mutant_names:
        filtered_mutants = [
            (m, key, result)
            for m, key, result in mutants
            if key in mutant_names or any(fnmatch.fnmatch(key, mutant_name) for mutant_name in mutant_names)
        ]
        assert filtered_mutants, f'Filtered for specific mutants, but nothing matches\n\nFilter: {mutant_names}'
        mutants = filtered_mutants
    return mutants, source_file_mutation_data_by_path


def estimated_worst_case_time(mutant_name):
    tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), set())
    return sum(mutmut.duration_by_test[t] for t in tests)


@cli.command()
@click.argument('mutant_names', required=False, nargs=-1)
def print_time_estimates(mutant_names):
    assert isinstance(mutant_names, (tuple, list)), mutant_names
    read_config()

    runner = PytestRunner()
    runner.prepare_main_test_run()

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    times_and_keys = [
        (estimated_worst_case_time(mutant_name), mutant_name)
        for m, mutant_name, result in mutants
    ]

    for time, key in sorted(times_and_keys):
        if not time:
            print(f'<no tests>', key)
        else:
            print(f'{int(time*1000)}ms', key)


@cli.command()
@click.argument('mutant_name', required=True, nargs=1)
def tests_for_mutant(mutant_name):
    if not load_stats():
        print('Failed to load stats. Please run mutmut first to collect stats.')
        exit(1)

    tests = tests_for_mutant_names([mutant_name])
    for test in sorted(tests):
        print(test)


def stop_all_children(mutants):
    for m, _, _ in mutants:
        m.stop_children()


@cli.command()
@click.option('--max-children', type=int)
@click.argument('mutant_names', required=False, nargs=-1)
def run(mutant_names, *, max_children):
    assert isinstance(mutant_names, (tuple, list)), mutant_names

    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!

    start = datetime.now()
    print('generating mutants')
    os.environ['MUTANT_UNDER_TEST'] = 'mutant_generation'
    read_config()
    create_mutants()
    copy_also_copy_files()
    time = datetime.now() - start
    print(f'    done in {round(time.total_seconds()*1000)}ms', )

    src_path = (Path('mutants') / 'src')
    source_path = (Path('mutants') / 'source')
    if src_path.exists():
        sys.path.insert(0, str(src_path.absolute()))
    elif source_path.exists():
        sys.path.insert(0, str(source_path.absolute))
    else:
        sys.path.insert(0, os.path.abspath('mutants'))

    # TODO: config/option for runner
    # runner = HammettRunner()
    runner = PytestRunner()
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test

    collect_or_load_stats(runner)

    mutants, source_file_mutation_data_by_path = collect_source_file_mutation_data(mutant_names=mutant_names)

    os.environ['MUTANT_UNDER_TEST'] = ''
    with CatchOutput(show_spinner=True, spinner_title='running clean tests') as output_catcher:
        tests = tests_for_mutant_names(mutant_names)

        clean_test_exit_code = runner.run_tests(mutant_name=None, tests=tests)
        if clean_test_exit_code != 0:
            output_catcher.dump_output()
            print('failed to run clean test')
            exit(1)
    print('    done')

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    run_forced_fail(runner)

    runner.prepare_main_test_run()

    def read_one_child_exit_status():
        pid, exit_code = os.wait()
        source_file_mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    source_file_mutation_data_by_pid: Dict[int, SourceFileMutationData] = {}  # many pids map to one MutationData
    running_children = 0
    if max_children is None:
        max_children = os.cpu_count() or 4

    count_tried = 0

    # Run estimated fast mutants first, calculated as the estimated time for a surviving mutant.
    mutants = sorted(mutants, key=lambda x: estimated_worst_case_time(x[1]))

    gc.freeze()

    start = datetime.now()
    try:
        print('Running mutation testing')

        for m, mutant_name, result in mutants:
            print_stats(source_file_mutation_data_by_path)

            mutant_name = mutant_name.replace('__init__.', '')

            # Rerun mutant if it's explicitly mentioned, but otherwise let the result stand
            if not mutant_names and result is not None:
                continue

            tests = mutmut.tests_by_mangled_function_name.get(mangled_name_from_mutant_name(mutant_name), [])

            # print(tests)
            if not tests:
                m.exit_code_by_key[mutant_name] = 33
                m.save()
                continue

            pid = os.fork()
            if not pid:
                # In the child
                os.environ['MUTANT_UNDER_TEST'] = mutant_name
                setproctitle(f'mutmut: {mutant_name}')

                # Run fast tests first
                tests = sorted(tests, key=lambda test_name: mutmut.duration_by_test[test_name])
                if not tests:
                    os._exit(33)

                estimated_time_of_tests = sum(mutmut.duration_by_test[test_name] for test_name in tests) + 1
                resource.setrlimit(resource.RLIMIT_CPU, (ceil(estimated_time_of_tests * 2), ceil(estimated_time_of_tests * 2)))

                with CatchOutput():
                    result = runner.run_tests(mutant_name=mutant_name, tests=tests)

                if result != 0:
                    # TODO: write failure information to stdout?
                    pass
                os._exit(result)
            else:
                # in the parent
                source_file_mutation_data_by_pid[pid] = m
                m.register_pid(pid=pid, key=mutant_name)
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
        print('stopping')
        stop_all_children(mutants)

    t = datetime.now() - start

    print_stats(source_file_mutation_data_by_path, force_output=True)
    print()
    print(f'{count_tried / t.total_seconds():.2f} mutations/second')

    if mutant_names:
        print()
        print('Mutant results')
        print('--------------')
        exit_code_by_key = {}
        # If the user gave a specific list of mutants, print result for these specifically
        for m, mutant_name, result in mutants:
            exit_code_by_key[mutant_name] = m.exit_code_by_key[mutant_name]

        for mutant_name, exit_code in sorted(exit_code_by_key.items()):
            print(emoji_by_status.get(status_by_exit_code.get(exit_code), '?'), mutant_name)

        print()


def tests_for_mutant_names(mutant_names):
    tests = set()
    for mutant_name in mutant_names:
        if '*' in mutant_name:
            for name, tests_of_this_name in mutmut.tests_by_mangled_function_name.items():
                if fnmatch.fnmatch(name, mutant_name):
                    tests |= set(tests_of_this_name)
        else:
            tests |= set(mutmut.tests_by_mangled_function_name[mangled_name_from_mutant_name(mutant_name)])
    return tests


@cli.command()
@click.option('--all', default=False)
def results(all):
    for path in walk_source_files():
        if not str(path).endswith('.py'):
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        for k, v in m.exit_code_by_key.items():
            status = status_by_exit_code[v]
            if status == 'killed' and not all:
                continue
            print(f'    {k}: {status}')


def read_mutants_ast(path):
    with open(Path('mutants') / path) as f:
        return parse(f.read(), error_recovery=False)


def read_orig_ast(path):
    with open(path) as f:
        return parse(f.read())


def find_ast_node(ast, function_name, orig_function_name):
    function_name = function_name.rpartition('.')[-1]
    orig_function_name = orig_function_name.rpartition('.')[-1]

    for node in ast.children:
        if node.type == 'classdef':
            (body,) = [x for x in node.children if x.type == 'suite']
            result = find_ast_node(body, function_name=function_name, orig_function_name=orig_function_name)
            if result:
                return result
        if node.type == 'funcdef' and node.name.value == function_name:
            node.name.value = orig_function_name
            return node


def read_original_ast_node(ast, mutant_name):
    orig_function_name, class_name = orig_function_and_class_names_from_key(mutant_name)
    orig_name = mangled_name_from_mutant_name(mutant_name) + '__mutmut_orig'

    result = find_ast_node(ast, function_name=orig_name, orig_function_name=orig_function_name)
    if not result:
        raise FileNotFoundError(f'Could not find original function "{orig_function_name}"')
    return result


def read_mutant_ast_node(ast, mutant_name):
    orig_function_name, class_name = orig_function_and_class_names_from_key(mutant_name)
    result = find_ast_node(ast, function_name=mutant_name, orig_function_name=orig_function_name)
    if not result:
        raise FileNotFoundError(f'Could not find mutant "{mutant_name}"')
    return result


def find_mutant(mutant_name):
    for path in walk_source_files():
        if mutmut.config.should_ignore_for_mutation(path):
            continue

        m = SourceFileMutationData(path=path)
        m.load()
        if mutant_name in m.exit_code_by_key:
            return m

    raise FileNotFoundError(f'Could not find mutant {mutant_name}')


def get_diff_for_mutant(mutant_name, source=None, path=None):
    if path is None:
        m = find_mutant(mutant_name)
        path = m.path
        status = status_by_exit_code[m.exit_code_by_key[mutant_name]]
    else:
        status = 'not checked'

    print(f'# {mutant_name}: {status}')

    if source is None:
        ast = read_mutants_ast(path)
    else:
        ast = parse(source, error_recovery=False)
    orig_code = read_original_ast_node(ast, mutant_name).get_code().strip()
    mutant_code = read_mutant_ast_node(ast, mutant_name).get_code().strip()

    path = str(path)  # difflib requires str, not Path
    return '\n'.join([
        line
        for line in unified_diff(orig_code.split('\n'), mutant_code.split('\n'), fromfile=path, tofile=path, lineterm='')
    ])


@cli.command()
@click.argument('mutant_name')
def show(mutant_name):
    read_config()
    print(get_diff_for_mutant(mutant_name))
    return


@cli.command()
@click.argument('mutant_name')
def apply(mutant_name):
    # try:
    read_config()
    apply_mutant(mutant_name)
    # except FileNotFoundError as e:
    #     print(e)


def apply_mutant(mutant_name):
    m = find_mutant(mutant_name)
    path = m.path

    orig_function_name, class_name = orig_function_and_class_names_from_key(mutant_name)
    orig_function_name = orig_function_name.rpartition('.')[-1]

    orig_ast = read_orig_ast(path)
    mutants_ast = read_mutants_ast(path)
    mutant_ast_node = read_mutant_ast_node(mutants_ast, mutant_name=mutant_name)

    mutant_ast_node.name.value = orig_function_name

    for node in orig_ast.children:
        if node.type == 'funcdef' and node.name.value == orig_function_name:
            node.children = mutant_ast_node.children
            break
    else:
        raise FileNotFoundError(f'Could not apply mutant {mutant_name}')

    with open(path, 'w') as f:
        f.write(orig_ast.get_code())


# TODO: junitxml, html commands

@cli.command()
def browse():
    from textual.app import App
    from textual.containers import Container
    from textual.widgets import Footer
    from textual.widgets import DataTable
    from textual.widgets import Static
    from textual.widget import Widget
    from rich.syntax import Syntax

    class ResultBrowser(App):
        loading_id = None
        CSS_PATH = "result_browser_layout.tcss"
        BINDINGS = [
            ("q", "quit()", "Quit"),
            ("r", "retest_mutant()", "Retest mutant"),
            ("f", "retest_function()", "Retest function"),
            ("m", "retest_module()", "Retest module"),
            ("a", "apply_mutant()", "Apply mutant to disk"),
        ]

        columns = [
            ('path', 'Path'),
        ] + [
            (status, emoji)
            for status, emoji in emoji_by_status.items()
        ]

        cursor_type = 'row'
        source_file_mutation_data_and_stat_by_path = None

        def compose(self):
            with Container(classes='container'):
                yield DataTable(id='files')
                yield DataTable(id='mutants')
            with Widget(id="diff_view_widget"):
                yield Static(id='diff_view')
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
            read_config()
            self.source_file_mutation_data_and_stat_by_path = {}

            for p in walk_source_files():
                if mutmut.config.should_ignore_for_mutation(p):
                    continue
                source_file_mutation_data = SourceFileMutationData(path=p)
                source_file_mutation_data.load()
                stat = collect_stat(source_file_mutation_data)

                self.source_file_mutation_data_and_stat_by_path[p] = source_file_mutation_data, stat

        def populate_files_table(self):
            files_table: DataTable = self.query_one('#files')
            # TODO: restore selection
            selected_row = files_table.cursor_row
            files_table.clear()

            for p, (source_file_mutation_data, stat) in sorted(self.source_file_mutation_data_and_stat_by_path.items()):
                row = [p] + [getattr(stat, k.replace(' ', '_')) for k, _ in self.columns[1:]]
                files_table.add_row(*row, key=p)

            files_table.move_cursor(row=selected_row)

        def on_data_table_row_highlighted(self, event):
            if not event.row_key or not event.row_key.value:
                return
            if event.data_table.id == 'files':
                mutants_table: DataTable = self.query_one('#mutants')
                mutants_table.clear()
                source_file_mutation_data, stat = self.source_file_mutation_data_and_stat_by_path[event.row_key.value]
                for k, v in source_file_mutation_data.exit_code_by_key.items():
                    status = status_by_exit_code[v]
                    if status == 'killed':
                        continue
                    mutants_table.add_row(k, emoji_by_status[status], key=k)
            else:
                assert event.data_table.id == 'mutants'
                diff_view = self.query_one('#diff_view')
                if event.row_key.value is None:
                    diff_view.update('')
                else:
                    diff_view.update('<loading...>')
                    self.loading_id = event.row_key.value

                    def load_thread():
                        read_config()
                        try:
                            d = get_diff_for_mutant(event.row_key.value)
                            if event.row_key.value == self.loading_id:
                                diff_view.update(Syntax(d, "diff"))
                        except Exception as e:
                            diff_view.update(f"<{type(e)} {e}>")

                    t = Thread(target=load_thread)
                    t.start()

        def retest(self, pattern):
            with self.suspend():
                assert sys.argv[-1] == 'browse'
                command = ' '.join([sys.executable] + sys.argv[:-1])
                os.system(f'{command} run "{pattern}"')
                input('press enter to return to browser')

            self.read_data()
            self.populate_files_table()

        def get_mutant_name_from_selection(self):
            mutants_table: DataTable = self.query_one('#mutants')
            if mutants_table.cursor_row is None:
                return

            return mutants_table.get_row_at(mutants_table.cursor_row)[0]

        def action_retest_mutant(self):
            self.retest(self.get_mutant_name_from_selection())

        def action_retest_function(self):
            self.retest(self.get_mutant_name_from_selection().rpartition('__mutmut_')[0] + '__mutmut_*')

        def action_retest_module(self):
            self.retest(self.get_mutant_name_from_selection().rpartition('.')[0] + '.*')

        def action_apply_mutant(self):
            read_config()
            mutants_table: DataTable = self.query_one('#mutants')
            if mutants_table.cursor_row is None:
                return
            apply_mutant(mutants_table.get_row_at(mutants_table.cursor_row)[0])

    ResultBrowser().run()


if __name__ == '__main__':
    cli()
