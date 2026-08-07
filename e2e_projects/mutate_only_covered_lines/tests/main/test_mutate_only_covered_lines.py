from mutate_only_covered_lines.ignore_me import this_function_shall_NOT_be_mutated
from mutate_only_covered_lines import hello_mutate_only_covered_lines, mutate_only_covered_lines_multiline, function_with_pragma, do_not_mutate_external_ommited_function
from mutate_only_covered_lines.exclude_me import excluded_function, excluded_branch, excluded_by_coverage_config, excluded_case

"""This tests the mutate_only_covered_lines feature."""

def test_mutate_only_covered_lines():
    assert hello_mutate_only_covered_lines(True) == "Hello from mutate_only_covered_lines! (true)"

def test_function_with_pragma():
    assert function_with_pragma() == 1

def test_mutate_only_covered_lines_multiline():
    assert mutate_only_covered_lines_multiline(True) == "Hello from mutate_only_covered_lines! (true) FooBar [0, 4, 8, 12, 16]"

def call_ignored_function():
    assert this_function_shall_NOT_be_mutated() == 3

def test_do_not_mutate_external_ommited_function():
    assert do_not_mutate_external_ommited_function() == 7

def test_excluded_function():
    assert excluded_function(1, 2) == 3

def test_excluded_branch():
    # both branches run, so the excluded one is covered and only its exclusion can save it
    assert excluded_branch(True) == 2
    assert excluded_branch(False) == 4

def test_excluded_by_coverage_config():
    assert excluded_by_coverage_config(2, 3) == 7

def test_excluded_case():
    assert excluded_case("a") == 1
    assert excluded_case("b") == 2
