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

from mutmut import (
    guess_paths_to_mutate,
    list_mutations,
    Context,
    mutate,
)

from tqdm import tqdm

from inspect import signature


_stats = set()


def record_trampoline_hit(name):
    _stats.add(name)


def get_stats():
    return _stats


def foo(a, *, b: int, **kwargs):
    pass


signature(foo)


def create_mutants():
    paths = [guess_paths_to_mutate()]
    next_id = 0
    function_by_id = {}
    for path in paths:
        for root, dirs, files in walk(path):
            for filename in files:
                if not filename.endswith('.py'):
                    continue
                if filename.endswith('__tests.py'):
                    continue
                if filename.startswith('test_.py'):
                    continue
                next_id = create_mutants_for_file(Path(root) / filename, next_id=next_id, function_by_id=function_by_id)
    return next_id, function_by_id


def write_trampoline(out, orig_name, mutant_names):
    print(file=out)

    def index(s):
        return s.rpartition('_')[-1]

    print(f'{orig_name}_mutants = {{' + ', '.join(f'{index(m)}: {m}' for m in mutant_names) + '}', file=out)

    print(file=out)
    print(f"""
def {orig_name}(*args, **kwargs):
    return trampoline({orig_name}_orig, {orig_name}_mutants, *args, **kwargs) 
 
""", file=out)
    print(f'{orig_name}.__signature__ = __signature({orig_name}_orig)\n', file=out)


def write_mutant(out, c, mutation_id, next_id, mutant_names, orig_name):
    if not mutation_id.subject_stack:
        return
    c.mutation_id = mutation_id
    new_code, number = mutate(c)
    node = mutation_id.subject_stack[-1]
    node.name.value += f'_mutant_{next_id}'
    mutant_names.append(node.name.value)
    # assert number == 1, number
    if number != 1:
        print(f'warning: got {number} mutations when mutating {mutation_id}')
    code = node.get_code()
    print(code.strip(), file=out)
    print(file=out)
    print(file=out)
    node.name.value = orig_name
    return node.get_code()


def write_original_alias(out, last_subject_stack):
    orig_name = last_subject_stack[-1].name.value
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
        mutant_under_test = -1
    return mutants.get(int(mutant_under_test), orig)(*args, **kwargs)

""", file=out)


def create_mutants_for_file(filename, next_id, function_by_id):
    output_path = Path('mutants') / filename
    makedirs(output_path.parent, exist_ok=True)

    input_stat = os.stat(filename)

    meta_filename = str(output_path) + '.next_id'

    # TODO: cache
    # if output_path.exists() and output_path.stat().st_mtime == input_stat.st_mtime:
    #     print('    skipped', output_path, 'already up to date')
    #     with open(meta_filename) as f:
    #         return int(f.read().strip())

    with open(output_path, 'w') as out:
        c = Context(filename=filename)
        # print('asd()', file=out)  # force invalid mutants file
        print(c.source, file=out)
        write_trampoline_impl(out)

        mutation_ids = list_mutations(c)

        mutant_names = []
        last_subject_stack = None

        last_code = None

        for mutation_id in mutation_ids:
            if not mutation_id.subject_stack:
                continue

            # TODO: mutate methods too!, then we have a classdef then a funcdef in the stack
            if mutation_id.subject_stack[0].type != 'funcdef':
                continue

            if last_subject_stack != mutation_id.subject_stack:
                if last_subject_stack:
                    write_original_alias(out, last_subject_stack)

                if mutant_names:
                    write_trampoline(out, orig_name, mutant_names)

                orig_name = mutation_id.subject_stack[0].name.value
                mutant_names = []
                last_subject_stack = mutation_id.subject_stack

            code = write_mutant(out, c, mutation_id, next_id, mutant_names, orig_name)
            module_name = str(filename)[:-len(filename.suffix)].replace(os.sep, ".").replace('.__init__', '')
            function_by_id[next_id] = f'{module_name}.{orig_name}'
            assert last_code != code
            last_code = code

            next_id += 1

        if last_subject_stack:
            write_original_alias(out, last_subject_stack)

        if mutant_names:
            write_trampoline(out, orig_name, mutant_names)

    # validate no syntax errors
    with open(output_path) as f:
        try:
            ast.parse(f.read())
        except (IndentationError, SyntaxError) as e:
            print(output_path, 'has invalid syntax: ', e)
            exit(1)

    os.utime(output_path, (input_stat.st_atime, input_stat.st_mtime))
    with open(meta_filename, 'w') as f:
        f.write(str(next_id))

    return next_id


def mutmut_3():
    # TODO: run no-ops once in a while to detect if we get false negatives

    start = datetime.now()
    print('generating mutants...')
    # TODO: read from db!!!!
    next_id, function_by_id = create_mutants()
    time = datetime.now() - start
    print('mutation generation', time)

    import sys
    import os
    import hammett

    sys.path.insert(0, os.path.abspath('mutants'))

    print('running baseline...')
    os.environ['MUTANT_UNDER_TEST'] = '-1'
    if hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True) != 0:
        print("FAILED")
        return
    print('done')

    print('running forced fail test')
    os.environ['MUTANT_UNDER_TEST'] = 'fail'
    if hammett.main(fail_fast=True, disable_assert_analyze=True) == 0:
        print("FAILED")
        return
    print('done')

    print('running stats...')
    os.environ['MUTANT_UNDER_TEST'] = 'stats'

    tests_by_function = defaultdict(set)

    def post_test_callback(_name, **_):
        for function in get_stats():
            tests_by_function[function].add(_name)
        _stats.clear()

    if hammett.main(quiet=True, fail_fast=True, disable_assert_analyze=True, post_test_callback=post_test_callback) != 0:
        print("FAILED")
        return
    print('done')

    db_path = Path('mutants') / 'db.json'
    try:
        with open(db_path) as f:
            db = json.loads(f.read())
            result_by_key = {int(k): v for k, v in db['result_by_key'].items()}
    except FileNotFoundError:
        result_by_key = {}

    def read_one_child_exit_status():
        pid, status = os.wait()
        result_by_key[key_from_pid[pid]] = (0xFF00 & status) >> 8  # The high byte contains the exit code

    hammett_kwargs = hammett.main_setup(
        quiet=True,
        fail_fast=True,
        disable_assert_analyze=True,
        use_cache=False,
    )

    key_from_pid = {}
    running_children = 0
    max_children = 8

    start = datetime.now()

    gc.freeze()

    count = 0

    try:
        print('Running mutation testing...')
        for key in tqdm(range(next_id)):
            if key in result_by_key:
                continue

            pid = os.fork()
            if not pid:
                sys.path.insert(0, os.path.abspath('mutants'))
                # In the child
                os.environ['MUTANT_UNDER_TEST'] = str(key)

                # TODO: this is needed for non-memory DBs
                hammett.Config.workerinput = dict(workerinput=f'_{key}')

                result = hammett.main_run_tests(**hammett_kwargs, tests=tests_by_function[function_by_id[key]])
                if result != 0:
                    # TODO: write failure information to stdout?
                    pass
                os._exit(result)
            else:
                key_from_pid[pid] = key
                running_children += 1

            if running_children >= max_children:
                read_one_child_exit_status()
                count += 1
                running_children -= 1

        try:
            while running_children:
                read_one_child_exit_status()
                count += 1
                running_children -= 1
        except ChildProcessError:
            pass
    except KeyboardInterrupt:
        print('aborting...')
    finally:
        with open(db_path, 'w') as f:
            json.dump(
                dict(
                    version=1,
                    result_by_key=result_by_key,
                    next_id=next_id,
                    function_by_id=function_by_id,
                ),
                f
            )

    t = datetime.now() - start

    covered = {k for k, v in result_by_key.items() if v != 0}
    not_covered = {k for k, v in result_by_key.items() if v == 0}
    print('covered:', covered)
    print('not covered:', not_covered)

    print('number of covered:', len(covered))
    print('number of not covered:', len(not_covered))
    print('%:', len(not_covered) / (len(covered) + len(not_covered)) * 100)

    print('time:', t)
    print('next ID:', next_id)
    print('number of tested mutants:', count)
    print('mutations/s:', count / t.total_seconds())


if __name__ == '__main__':
    mutmut_3()
