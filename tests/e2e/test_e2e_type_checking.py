from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_type_checking_result_snapshot():
    assert run_mutmut_on_project("type_checking") == snapshot(
        {
            "mutants/src/type_checking/__init__.py.meta": {
                "type_checking.x_hello__mutmut_1": 6,
                "type_checking.x_hello__mutmut_2": 1,
                "type_checking.x_hello__mutmut_3": 1,
                "type_checking.x_hello__mutmut_4": 1,
                "type_checking.x_a_hello_wrapper__mutmut_1": 6,
                "type_checking.x_a_hello_wrapper__mutmut_2": 0,
                "type_checking.xǁPersonǁset_name__mutmut_1": 6,
                "type_checking.x_mutate_me__mutmut_1": 6,
                "type_checking.x_mutate_me__mutmut_2": 6,
                "type_checking.x_mutate_me__mutmut_3": 1,
                "type_checking.x_mutate_me__mutmut_4": 1,
                "type_checking.x_mutate_me__mutmut_5": 6,
            }
        }
    )
