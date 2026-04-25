from config_pkg.math import func_with_no_tests

# ignored, because pytest_add_cli_args_test_selection specifies only the main directory
def test_include_func_with_no_tests():
    assert func_with_no_tests() == 420
