from mutate_only_covered_lines import hello_mutate_only_covered_lines, mutate_only_covered_lines_multiline

"""This tests the mutate_only_covered_lines feature."""

def test_mutate_only_covered_lines():
    assert hello_mutate_only_covered_lines(True) == "Hello from mutate_only_covered_lines! (true)"

def test_mutate_only_covered_lines_multiline():
    assert mutate_only_covered_lines_multiline(True) == "Hello from mutate_only_covered_lines! (true) FooBar [0, 4, 8, 12, 16]"