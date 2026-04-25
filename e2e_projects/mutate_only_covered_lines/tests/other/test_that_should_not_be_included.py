from mutate_only_covered_lines import hello_mutate_only_covered_lines

"""This test should be ignored, because of the pytest_add_cli_args_test_selection config."""

def test_mutate_only_covered_lines():
    assert hello_mutate_only_covered_lines(False) == "Hello from mutate_only_covered_lines! (false)"
