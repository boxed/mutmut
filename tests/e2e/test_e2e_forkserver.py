from inline_snapshot import snapshot

from tests.e2e.e2e_utils import run_mutmut_on_project


def test_forkserver_result_snapshot():
    """The forkserver_basic project sets ``process_isolation = "forkserver"``."""
    assert run_mutmut_on_project("forkserver_basic") == snapshot(
        {
            "mutants/src/fs_calc/__init__.py.meta": {
                "fs_calc.x_add__mutmut_1": 1,
                "fs_calc.x_sub__mutmut_1": 1,
                "fs_calc.x_mul__mutmut_1": 1,
                "fs_calc.x_untested__mutmut_1": 33,
                "fs_calc.x_untested__mutmut_2": 33,
            }
        }
    )
