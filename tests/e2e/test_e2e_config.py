from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_config_result_snapshot():
    assert run_mutmut_on_project("config") == snapshot(
        {
            "mutants/config_pkg/__init__.py.meta": {
                "config_pkg.x_hello__mutmut_1": 1,
                "config_pkg.x_hello__mutmut_2": 1,
                "config_pkg.x_hello__mutmut_3": 1,
            },
            "mutants/config_pkg/math.py.meta": {
                "config_pkg.math.x_add__mutmut_1": 0,
                "config_pkg.math.x_call_depth_two__mutmut_1": 1,
                "config_pkg.math.x_call_depth_two__mutmut_2": 1,
                "config_pkg.math.x_call_depth_three__mutmut_1": 1,
                "config_pkg.math.x_call_depth_three__mutmut_2": 1,
                "config_pkg.math.x_call_depth_four__mutmut_1": 33,
                "config_pkg.math.x_call_depth_four__mutmut_2": 33,
                "config_pkg.math.x_call_depth_five__mutmut_1": 33,
                "config_pkg.math.x_func_with_no_tests__mutmut_1": 33,
            },
        }
    )
