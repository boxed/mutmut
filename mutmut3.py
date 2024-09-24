import itertools
import os
import ast
import gc
import json
import shutil
import sys
from collections import defaultdict
from contextlib import contextmanager
from datetime import (
    datetime,
    timedelta,
)
from difflib import unified_diff
from io import TextIOBase
from os import (
    makedirs,
    walk,
)
from pathlib import Path
from typing import Dict

import click
from parso import parse

import mutmut
from mutmut import guess_paths_to_mutate

mutmut._stats = set()


exit_code_to_status = {
    1: 'killed',
    0: 'survived',
}


def record_trampoline_hit(name):
    mutmut._stats.add(name)


def walk_files():
    paths = [guess_paths_to_mutate()]
    for path in paths:
        for root, dirs, files in walk(path):
            for filename in files:
                if filename.endswith('.pyc'):
                    continue
                if filename.endswith('__tests.py'):
                    continue
                if filename.startswith('test_.py'):
                    continue
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
    prefix = orig.__module__ + '.'
    # if not mutant_under_test.startswith(prefix):
    #     return orig(*args, **kwargs)
    return mutants[mutant_under_test[len(prefix):]](*args, **kwargs)

"""


def create_mutants():
    for path in walk_files():
        output_path = Path('mutants') / path
        makedirs(output_path.parent, exist_ok=True)

        if str(path).endswith('.py'):
            create_mutants_for_file(path, output_path)
        else:
            shutil.copy(path, output_path)


def create_mutants_for_file(filename, output_path):

    input_stat = os.stat(filename)

    if output_path.exists() and output_path.stat().st_mtime == input_stat.st_mtime:
        # print('    skipped', output_path, 'already up to date')
        return

    mutant_names = []

    with open(filename) as f:
        source = f.read()

    with open(output_path, 'w') as out:
        for x, mutant_name in yield_mutants_for_module(parse(source)):
            out.write('\n\n')
            out.write(x)
            if mutant_name:
                mutant_names.append(mutant_name)

    # validate no syntax errors
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
        ), f)

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))


def build_trampoline(orig_name, mutants):
    mutants_dict = f'{orig_name}__mutmut_mutants = {{\n' + ', \n    '.join(f'{repr(m)}: {m}' for m in mutants) + ',\n}'

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
        if context.exclude_line():
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
    def __init__(self):
        self.count = 0
        self.mutants = []
        self.stack = []
        self.dict_synonyms = {}

    def exclude_line(self):
        return False


def yield_mutants_for_function(node):
    assert node.type == 'funcdef'

    with rename(node, suffix='orig'):
        yield node.get_code(), None

    context = FuncContext()

    for child_node in node.children:
        context.stack.append(child_node)
        try:
            yield from yield_mutants_for_node(func_node=node, node=child_node, context=context)
        finally:
            context.stack.pop()

    yield build_trampoline(node.name.value, context.mutants), None


def yield_mutants_for_class(node):
    assert node.type == 'classdef'
    yield node.get_code(), None


def yield_mutants_for_module(node):
    yield trampoline_impl, None
    yield '\n', None
    assert node.type == 'file_input'
    for child_node in node.children:
        # TODO: support methods
        if child_node.type == 'funcdef':
            yield from yield_mutants_for_function(child_node)
        elif child_node.type == 'classdef':
            yield from yield_mutants_for_class(child_node)
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
            ), f)


def unused(*_):
    pass


# For pytest. This function gets installed by pytest's plugin system
def pytest_runtest_teardown(item, nextitem):
    unused(nextitem)
    for function in mutmut._stats:
        mutmut.tests_by_function[function].add(item._nodeid)
    mutmut._stats.clear()


class TestRunner:
    def run_stats(self):
        raise NotImplementedError()

    def run_forced_fail(self):
        raise NotImplementedError()

    def prepare_main_test_run(self):
        pass

    def run_tests(self, *, key, tests):
        raise NotImplementedError()


class PytestRunner(TestRunner):
    def run_stats(self):
        import pytest
        return int(pytest.main(['-p', 'mutmut3', '-x', '-q', '--assert=plain']))

    def run_tests(self, *, key, tests):
        import pytest
        return int(pytest.main(['-x', '-q', '--assert=plain'] + list(tests)))

    def run_forced_fail(self):
        import pytest
        return int(pytest.main(['-x', '-q', '--assert=plain']))


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
        # if not force_output and (last_update[0] - datetime.now()) < update_threshold:
        #     return
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        sys.__stdout__.write(output)
        sys.__stdout__.flush()
        last_len[0] = len_s
    return p


print_status = status_printer()


def print_stats(mutation_data_by_path, force_output=False):
    not_checked = 0
    killed = 0
    survived = 0
    total = 0
    for m in mutation_data_by_path.values():
        for k, v in m.result_by_key.items():
            total += 1
            if v is None:
                not_checked += 1
            else:
                if v == 0:
                    survived += 1
                else:
                    killed += 1
    skipped = 0  # TODO
    suspicious = 0  # TODO
    timed_out = 0  # TODO
    print_status('{}/{}  🎉 {}  ⏰ {}  🤔 {}  🙁 {}  🔇 {}'.format((total - not_checked), total, killed, timed_out, suspicious, survived, skipped), force_output=force_output)


def run_forced_fail(runner):
    os.environ['MUTANT_UNDER_TEST'] = 'fail'
    try:
        if runner.run_forced_fail() == 0:
            print("FAILED")
            os._exit(1)
    except MutmutProgrammaticFailException:
        pass


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

    def __enter__(self):
        sys.stdout = self.redirect
        sys.stderr = self.redirect

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


@click.group()
def cli():
    pass


@cli.command()
def run():
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!

    start = datetime.now()
    print('generating mutants...')
    create_mutants()
    time = datetime.now() - start
    print(f'    done in {round(time.total_seconds()*1000)}ms', )

    sys.path.insert(0, os.path.abspath('mutants'))

    runner = HammettRunner()
    # runner = PytestRunner()
    runner.prepare_main_test_run()

    # TODO: run these steps only if we have mutants to test
    print('running stats...')
    os.environ['MUTANT_UNDER_TEST'] = 'stats'
    mutmut.tests_by_function = defaultdict(set)
    with CatchOutput():
        if runner.run_stats():
            print("FAILED")
            return
    print('    done')

    runner.prepare_main_test_run()

    if not mutmut.tests_by_function:
        print('failed to collect stats')
        return

    # this can't be the first thing, because it can fail deep inside pytest/django setup and then everything is destroyed
    print('running forced fail test')
    with CatchOutput():
        run_forced_fail(runner)
    print('    done')

    runner.prepare_main_test_run()

    def read_one_child_exit_status():
        pid, exit_code = os.wait()
        mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    mutation_data_by_path: Dict[str, MutationData] = {}
    mutation_data_by_pid: Dict[int, MutationData] = {}  # many pids map to one MutationData
    running_children = 0
    max_children = os.cpu_count()

    start = datetime.now()

    total_count = 0

    for path in walk_files():
        if not str(path).endswith('.py'):
            continue
        assert path not in mutation_data_by_path
        m = MutationData(path=path)
        mutation_data_by_path[str(path)] = m

    mutants = [
        (m, key, result)
        for path, m in mutation_data_by_path.items()
        for key, result in m.result_by_key.items()
    ]

    gc.freeze()

    try:
        print('Running mutation testing...')

        for m, key, result in mutants:
            print_stats(mutation_data_by_path)

            key = key.replace('__init__.', '')
            if result is not None:
                continue

            # # single threaded:
            # runner.prepare_main_test_run()
            # os.environ['MUTANT_UNDER_TEST'] = key
            # function = function_name_from_key(key)
            # tests = mutmut.tests_by_function[function]
            # result = runner.run_tests(key=key, tests=tests)

            pid = os.fork()
            if not pid:
                # In the child
                os.environ['MUTANT_UNDER_TEST'] = key
                function = orig_function_name_from_key(key)

                tests = mutmut.tests_by_function[function]
                if not tests:
                    print(f'  no tests covers {function}')
                    os._exit(1)

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
                total_count += 1
                running_children -= 1

        try:
            while running_children:
                read_one_child_exit_status()
                total_count += 1
                running_children -= 1
        except ChildProcessError:
            pass
    except KeyboardInterrupt:
        print('aborting...')

    t = datetime.now() - start

    print_stats(mutation_data_by_path, force_output=True)
    print()
    print('mutations/s:', total_count / t.total_seconds())


@cli.command()
def results():
    for path in walk_files():
        if not str(path).endswith('.py'):
            continue
        m = MutationData(path=path)
        print(path)
        for k, v in m.result_by_key.items():
            print(f'    {k}: {exit_code_to_status[v]}')


def read_original_ast(path):
    with open(path) as f:
        return parse(f.read())


def read_original_ast_node(path, orig_function_name):
    orig_ast = read_original_ast(path)

    for node in orig_ast.children:
        if node.type == 'funcdef' and node.name.value == orig_function_name:
            return node

    print(f'Could not find original function {orig_function_name}')
    exit(0)


def read_mutant_ast_node(path, orig_function_name, mutant_function_name):
    with open(Path('mutants') / path) as f:
        mutants_ast = parse(f.read())

    for node in mutants_ast.children:
        if node.type == 'funcdef' and node.name.value == mutant_function_name:
            node.name.value = orig_function_name
            return node

    print(f'Could not find mutant function {mutant_function_name}')
    exit(0)


def find_mutant(mutant_name):
    for path in walk_files():
        if not str(path).endswith('.py'):
            continue

        m = MutationData(path=path)
        if mutant_name in m.result_by_key:
            return m

    print(f'Could not find mutant {mutant_name}')
    exit(0)


@cli.command()
@click.argument('mutant_name')
def show(mutant_name):
    m = find_mutant(mutant_name)
    path = m.path

    print(f'# {mutant_name}: {exit_code_to_status[m.result_by_key[mutant_name]]}')

    orig_function_name = orig_function_name_from_key(mutant_name).partition('.')[2]
    mutant_function_name = mutant_name.partition('.')[2]

    orig_code = read_original_ast_node(path, orig_function_name).get_code().strip()
    mutant_code = read_mutant_ast_node(path, orig_function_name, mutant_function_name).get_code().strip()

    path = str(path)  # difflib requires str, not Path
    for line in unified_diff(orig_code.split('\n'), mutant_code.split('\n'), fromfile=path, tofile=path, lineterm=''):
        print(line)

    return


@cli.command()
@click.argument('mutant_name')
def apply(mutant_name):
    m = find_mutant(mutant_name)
    path = m.path

    orig_function_name = orig_function_name_from_key(mutant_name).partition('.')[2]
    mutant_function_name = mutant_name.partition('.')[2]
    mutant_ast_node = read_mutant_ast_node(path, orig_function_name, mutant_function_name)

    orig_ast = read_original_ast(path)
    for node in orig_ast.children:
        if node.type == 'funcdef' and node.name.value == orig_function_name:
            node.children = mutant_ast_node.children
            break
    else:
        print(f'Could apply mutant {orig_function_name}')
        exit(0)

    with open(path, 'w') as f:
        f.write(orig_ast.get_code())

# TODO: junitxml, html


if __name__ == '__main__':
    cli()
