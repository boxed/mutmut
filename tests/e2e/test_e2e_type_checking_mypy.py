from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_type_checking_mypy_result_snapshot():
    assert run_mutmut_on_project("type_checking_mypy") == snapshot(
        {
            "mutants/src/type_checking_mypy/__init__.py.meta": {
                "type_checking_mypy.x_hello__mutmut_1": 37,
                "type_checking_mypy.x_hello__mutmut_2": 1,
                "type_checking_mypy.x_hello__mutmut_3": 1,
                "type_checking_mypy.x_hello__mutmut_4": 1,
                "type_checking_mypy.x_mutate_me__mutmut_1": 37,
                "type_checking_mypy.x_mutate_me__mutmut_2": 1,
                "type_checking_mypy.x_mutate_me__mutmut_3": 1,
                "type_checking_mypy.x_mutate_me__mutmut_4": 1,
            }
        }
    )
