import ast
import gc
import json
import os
from collections import defaultdict
from datetime import datetime
from os import (
    makedirs,
    walk,
)
from pathlib import Path
from typing import Dict

from tqdm import tqdm

from mutmut import (
    Context,
    guess_paths_to_mutate,
    list_mutations,
    mutate,
)
import mutmut

mutmut._stats = set()


def record_trampoline_hit(name):
    mutmut._stats.add(name)


def walk_files():
    paths = [guess_paths_to_mutate()]
    for path in paths:
        for root, dirs, files in walk(path):
            for filename in files:
                if not filename.endswith('.py'):
                    continue
                if filename.endswith('__tests.py'):
                    continue
                if filename.startswith('test_.py'):
                    continue
                yield Path(root) / filename


def create_mutants():
    for path in walk_files():
        create_mutants_for_file(path)


def write_trampoline(out, orig_name, mutant_names):
    print(file=out)

    def func_name(s):
        return s.rpartition('.')[-1].replace('$', '_mutant_')

    print(f'{orig_name}_mutants = {{' + ', '.join(f'{repr(m)}: {func_name(m)}' for m in mutant_names) + '}', file=out)

    print(file=out)
    print(f"""
def {orig_name}(*args, **kwargs):
    return trampoline({orig_name}_orig, {orig_name}_mutants, *args, **kwargs) 
 
""", file=out)
    print(f'{orig_name}.__signature__ = __signature({orig_name}_orig)\n', file=out)


class InvalidMutantException(Exception):
    pass


def write_mutant(out, c, mutation_id, next_id, orig_name, module_name):
    if not mutation_id.subject:
        return
    c.mutation_id = mutation_id
    new_code, number = mutate(c)
    node = mutation_id.subject
    try:
        node.name.value += f'_mutant_{next_id}'
        mutant_name = f'{module_name}.{orig_name}${next_id}'
        # assert number == 1, number
        if number != 1:
            print(f'warning: got {number} mutations when mutating {mutation_id}')
        code = node.get_code()

        try:
            ast.parse(code)
        except (IndentationError, SyntaxError):
            raise InvalidMutantException()

        print(code.strip(), file=out)
        print(file=out)
        print(file=out)
        return node.get_code(), mutant_name
    finally:
        node.name.value = orig_name


def write_original_alias(out, last_subject):
    orig_name = last_subject.name.value
    print(f'{orig_name}_orig = {orig_name}', file=out)  # the trampoline will then overwrite the original


def write_trampoline_impl(out):
    # language=python
    print("""
from inspect import signature as __signature


def trampoline(orig, mutants, *args, **kwargs):
    import os
    mutant_under_test = os.environ['MUTANT_UNDER_TEST']
    if mutant_under_test == 'fail':
        raise Exception('Failed programmatically')      
    elif mutant_under_test == 'stats':
        from __main__ import record_trampoline_hit
        record_trampoline_hit(orig.__module__ + '.' + orig.__name__)
        mutant_under_test = '..matches nothing..'
    prefix = orig.__module__ + '.' + orig.__name__ + '$'
    if not mutant_under_test.startswith(prefix):
        return orig(*args, **kwargs)
    return mutants[mutant_under_test](*args, **kwargs)

""", file=out)


def create_mutants_for_file(filename):
    output_path = Path('mutants') / filename
    makedirs(output_path.parent, exist_ok=True)

    input_stat = os.stat(filename)

    if output_path.exists() and output_path.stat().st_mtime == input_stat.st_mtime:
        # print('    skipped', output_path, 'already up to date')
        return

    result_by_key = {}

    with open(output_path, 'w') as out:
        c = Context(filename=filename)
        # print('asd()', file=out)  # force invalid mutants file
        print(c.source, file=out)
        write_trampoline_impl(out)

        mutation_ids = list_mutations(c)

        mutant_names = []
        last_subject = None

        last_code = None

        next_id = 0
        for mutation_id in mutation_ids:
            if not mutation_id.subject:
                continue

            # TODO: mutate methods too!, then we have a classdef then a funcdef in the stack
            if mutation_id.subject.type != 'funcdef':
                continue

            if last_subject != mutation_id.subject:
                if last_subject:
                    write_original_alias(out, last_subject)

                if mutant_names:
                    write_trampoline(out, orig_name, mutant_names)

                orig_name = mutation_id.subject.name.value
                mutant_names = []
                last_subject = mutation_id.subject
                next_id = 0

            next_id += 1

            module_name = str(filename)[:-len(filename.suffix)].replace(os.sep, ".").replace('.__init__', '')

            try:
                code, mutant_name = write_mutant(out, c, mutation_id, next_id, orig_name, module_name)
            except InvalidMutantException:
                continue


            result_by_key[mutant_name] = None
            mutant_names.append(mutant_name)

            assert last_code != code
            last_code = code

        if last_subject:
            write_original_alias(out, last_subject)

        if mutant_names:
            write_trampoline(out, orig_name, mutant_names)

    # validate no syntax errors
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            print(output_path, 'has invalid syntax: ', e)
            exit(1)

    meta_filename = str(output_path) + '.meta'
    with open(meta_filename, 'w') as f:
        json.dump(dict(
            result_by_key=result_by_key,
        ), f)

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))


class MutationData:
    def __init__(self, *, path):
        self.meta_path = Path('mutants') / (str(path) + '.meta')
        with open(self.meta_path) as f:
            self.meta = json.load(f)

        self.key_by_pid = {}
        self.result_by_key = self.meta.pop('result_by_key')
        assert not self.meta, self.meta  # We should read all the data!

    def register_pid(self, *, pid, key):
        self.key_by_pid[pid] = key

    def register_result(self, *, pid, exit_code):
        self.result_by_key[self.key_by_pid[pid]] = (0xFF00 & exit_code) >> 8  # The high byte contains the exit code
        self.save()


    def save(self):
        with open(self.meta_path, 'w') as f:
            json.dump(dict(
                result_by_key=self.result_by_key,
            ), f)


# For pytest
def pytest_runtest_teardown(item, nextitem):
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

        def post_test_callback(_name, **_):
            for function in mutmut._stats:
                mutmut.tests_by_function[function].add(_name)
            mutmut._stats.clear()

        return hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, post_test_callback=post_test_callback, use_cache=False)

    def run_forced_fail(self):
        import hammett
        return hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, use_cache=False)

    def prepare_main_test_run(self):
        import hammett
        self.hammett_kwargs = hammett.main_setup(
            quiet=True,
            fail_fast=True,
            disable_assert_analyze=True,
            use_cache=False,
        )

    def run_tests(self, *, key, tests):
        import hammett
        hammett.Config.workerinput = dict(workerinput=f'_{key}')
        return hammett.main_run_tests(**self.hammett_kwargs, tests=tests)


def function_name_from_key(key):
    return key.rpartition('$')[0]


def mutmut_3():
    # TODO: run no-ops once in a while to detect if we get false negatives
    # TODO: we should be able to get information on which tests killed mutants, which means we can get a list of tests and how many mutants each test kills. Those that kill zero mutants are redundant!

    start = datetime.now()
    print('generating mutants...')
    create_mutants()
    time = datetime.now() - start
    print('mutation generation', time)

    import sys
    import os

    sys.path.insert(0, os.path.abspath('mutants'))

    runner = HammettRunner()

    # TODO: run these steps only if we have mutants to test
    print('running stats...')
    os.environ['MUTANT_UNDER_TEST'] = 'stats'
    mutmut.tests_by_function = defaultdict(set)
    if runner.run_stats():
        print("FAILED")
        return
    print('done')

    return

    if not mutmut.tests_by_function:
        print('failed to collect stats')
        return

    print('running forced fail test')
    os.environ['MUTANT_UNDER_TEST'] = 'fail'
    try:
        if runner.run_forced_fail() == 0:
            print("FAILED")
            return
    except Exception as e:
        # We get here if there's a mutant in the setup code path
        assert e.args[0] == 'Failed programmatically'
    print('done')

    def read_one_child_exit_status():
        pid, exit_code = os.wait()
        mutation_data_by_pid[pid].register_result(pid=pid, exit_code=exit_code)

    runner.prepare_main_test_run()

    mutation_data_by_path : Dict[str, MutationData] = {}
    mutation_data_by_pid : Dict[int, MutationData] = {}  # many pids map to one MutationData
    running_children = 0
    max_children = os.cpu_count()

    start = datetime.now()

    gc.freeze()

    total_count = 0

    try:
        print('Running mutation testing...')
        for path in tqdm(walk_files()):  # TODO: now the progress bar is per file, which sucks a bit
            assert path not in mutation_data_by_path
            m = MutationData(path=path)
            mutation_data_by_path[str(path)] = m

            for key, result in m.result_by_key.items():
                if result is not None:
                    continue

                pid = os.fork()
                if not pid:
                    sys.path.insert(0, os.path.abspath('mutants'))
                    # In the child
                    os.environ['MUTANT_UNDER_TEST'] = key

                    function = function_name_from_key(key)

                    tests = mutmut.tests_by_function[function]
                    if not tests:
                        print(f'  no tests covers {function}')
                        os._exit(1)

                    result = runner.run_tests(key=key, tests=tests)
                    if result != 0:
                        # TODO: write failure information to stdout?
                        pass
                    os._exit(result)
                else:
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

    covered = {k for m in mutation_data_by_path.values() for k, v in m.result_by_key.items() if v != 0}
    not_covered = {k for m in mutation_data_by_path.values() for k, v in m.result_by_key.items() if v == 0}

    print('number of covered:', len(covered))
    print('number of not covered:', len(not_covered))
    print('%:', len(not_covered) / (len(covered) + len(not_covered)) * 100)

    print('time:', t)
    print('number of tested mutants:', total_count)
    print('mutations/s:', total_count / t.total_seconds())


if __name__ == '__main__':
    mutmut_3()
