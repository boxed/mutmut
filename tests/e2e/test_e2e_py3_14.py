from inline_snapshot import snapshot
import pytest
import sys

from tests.e2e.e2e_utils import run_mutmut_on_project


@pytest.mark.skipif(
    sys.version_info < (3, 14), reason="Can only test python 3.14 features on 3.14"
)
def test_python_3_14_result_snapshot():
    assert run_mutmut_on_project("py3_14_features") == snapshot(
        {
            "mutants/src/py3_14_features/__init__.py.meta": {
                "py3_14_features.x_get_len__mutmut_1": 0,
                "py3_14_features.x_get_len__mutmut_2": 1,
                "py3_14_features.x_get_foo_len__mutmut_1": 0,
                "py3_14_features.x_get_foo_len__mutmut_2": 1,
            }
        }
    )
