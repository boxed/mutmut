from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_src_package_result_snapshot():
    assert run_mutmut_on_project("src_package") == snapshot(
        {
            "mutants/src/__init__.py.meta": {},
            "mutants/src/calculator.py.meta": {
                "src.calculator.x_add_one__mutmut_1": 1,
                "src.calculator.x_add_one__mutmut_2": 1,
            },
        }
    )
