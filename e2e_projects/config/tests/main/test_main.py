import json
from pathlib import Path
from config_pkg import hello
from config_pkg.math import add, call_depth_two
from config_pkg.ignore_me import this_function_shall_NOT_be_mutated

def test_hello():
    assert hello() == "Hello from config!"

def test_add():
    assert add(1, 0) == 1

def test_non_mutated_function():
    assert this_function_shall_NOT_be_mutated() == 3

def test_max_stack_depth():
    # This test should only cover functions up to some depth
    # For more context, see https://github.com/boxed/mutmut/issues/378
    assert call_depth_two() == 2

def test_data_exists():
    path = (Path("data") / "data.json").resolve()
    assert path.exists()
    with open(path) as f:
        data = json.load(f)
        assert data['comment'] == 'this should be copied to the mutants folder'