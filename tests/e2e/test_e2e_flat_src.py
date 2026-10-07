from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_flat_src_result_snapshot():
    """Flat layout (`src` IS the import package): mutants are named with the
    full `src.` module prefix and the suite kills/survives as expected."""
    assert run_mutmut_on_project("flat_src") == snapshot(
        {
            "mutants/src/__init__.py.meta": {
                "src.x_version__mutmut_1": 1,
                "src.x_version__mutmut_2": 1,
            },
            "mutants/src/calc.py.meta": {
                "src.calc.x_hello__mutmut_1": 1,
                "src.calc.x_hello__mutmut_2": 1,
                "src.calc.x_hello__mutmut_3": 1,
                "src.calc.x_add__mutmut_1": 1,
                "src.calc.x_clamp__mutmut_1": 0,
                "src.calc.x_clamp__mutmut_2": 0,
                "src.calc.x_badly_tested__mutmut_1": 0,
                "src.calc.x_badly_tested__mutmut_2": 0,
                "src.calc.x_badly_tested__mutmut_3": 0,
            },
        }
    )
