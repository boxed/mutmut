from mutate_only_covered_lines.ignore_me import this_function_shall_NOT_be_mutated
from mutate_only_covered_lines import hello_mutate_only_covered_lines, mutate_only_covered_lines_multiline, function_with_pragma

"""This tests the mutate_only_covered_lines feature."""

def test_mutate_only_covered_lines():
    assert hello_mutate_only_covered_lines(True) == "Hello from mutate_only_covered_lines! (true)"

def test_function_with_pragma():
    assert function_with_pragma() == 1

def test_mutate_only_covered_lines_multiline():
    assert mutate_only_covered_lines_multiline(True) == "Hello from mutate_only_covered_lines! (true) FooBar [0, 4, 8, 12, 16]"

def call_ignored_function():
    assert this_function_shall_NOT_be_mutated() == 3