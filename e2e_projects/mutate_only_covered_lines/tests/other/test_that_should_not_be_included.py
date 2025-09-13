from mutate_only_covered_lines import hello_mutate_only_covered_lines

"""This test should be ignored, because of the tests_dir config."""

def test_mutate_only_covered_lines():
    assert hello_mutate_only_covered_lines(False) == "Hello from mutate_only_covered_lines! (false)"
