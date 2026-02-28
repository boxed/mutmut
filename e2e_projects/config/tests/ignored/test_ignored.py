from config_pkg.math import func_with_no_tests

# ignored, because tests_dir specifies only the main directory
def test_include_func_with_no_tests():
    assert func_with_no_tests() == 420
