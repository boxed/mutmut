import json
import pytest
from pathlib import Path
from config_pkg import hello
from config_pkg.math import add, call_depth_two
from config_pkg.ignore_me import this_function_shall_NOT_be_mutated

def test_include_hello():
    assert hello() == "Hello from config!"

def test_include_add():
    assert add(1, 0) == 1

def test_include_non_mutated_function():
    assert this_function_shall_NOT_be_mutated() == 3

def test_include_max_stack_depth():
    # This test should only cover functions up to some depth
    # For more context, see https://github.com/boxed/nootnoot/issues/378
    assert call_depth_two() == 2

def test_include_data_exists():
    path = (Path("data") / "data.json").resolve()
    assert path.exists()
    with open(path) as f:
        data = json.load(f)
        assert data['comment'] == 'this should be copied to the mutants folder'

# ignored, because it does not match -k 'test_include' 
def test_should_be_ignored():
    assert 'This test should be ignored' == 1234

@pytest.mark.xfail
def test_include_xfail_that_does_not_fail():
    # verify that we can override the xfail=strict from the pytest settings
    assert 1 == 1

# ignored, because of -m 'not fail'
@pytest.mark.fail
def test_include_that_should_be_ignored():
    assert 'This test should be ignored' == 1234