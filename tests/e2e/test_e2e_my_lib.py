from inline_snapshot import snapshot

import mutmut
from mutmut.__main__ import _run
from mutmut.runners.harness import PytestRunner
from tests.e2e.e2e_utils import E2E_PROJECTS
from tests.e2e.e2e_utils import change_cwd
from tests.e2e.e2e_utils import run_mutmut_on_project


def test_my_lib_result_snapshot():
    assert run_mutmut_on_project("my_lib") == snapshot(
        {
            "mutants/src/my_lib/__init__.py.meta": {
                "my_lib.x_hello__mutmut_1": 1,
                "my_lib.x_hello__mutmut_2": 1,
                "my_lib.x_hello__mutmut_3": 1,
                "my_lib.x_badly_tested__mutmut_1": 0,
                "my_lib.x_badly_tested__mutmut_2": 0,
                "my_lib.x_badly_tested__mutmut_3": 0,
                "my_lib.x_untested__mutmut_1": 33,
                "my_lib.x_untested__mutmut_2": 33,
                "my_lib.x_untested__mutmut_3": 33,
                "my_lib.x_make_greeter__mutmut_1": 1,
                "my_lib.x_make_greeter__mutmut_2": 1,
                "my_lib.x_make_greeter__mutmut_3": 1,
                "my_lib.x_make_greeter__mutmut_4": 1,
                "my_lib.x_make_greeter__mutmut_5": 0,
                "my_lib.x_make_greeter__mutmut_6": 0,
                "my_lib.x_make_greeter__mutmut_7": 0,
                "my_lib.x_fibonacci__mutmut_1": 1,
                "my_lib.x_fibonacci__mutmut_2": 0,
                "my_lib.x_fibonacci__mutmut_3": 0,
                "my_lib.x_fibonacci__mutmut_4": 0,
                "my_lib.x_fibonacci__mutmut_5": 0,
                "my_lib.x_fibonacci__mutmut_6": 0,
                "my_lib.x_fibonacci__mutmut_7": 0,
                "my_lib.x_fibonacci__mutmut_8": 0,
                "my_lib.x_fibonacci__mutmut_9": 0,
                "my_lib.x_async_consumer__mutmut_1": 1,
                "my_lib.x_async_consumer__mutmut_2": 1,
                "my_lib.x_async_generator__mutmut_1": 1,
                "my_lib.x_async_generator__mutmut_2": 1,
                "my_lib.x_simple_consumer__mutmut_1": 1,
                "my_lib.x_simple_consumer__mutmut_2": 1,
                "my_lib.x_simple_consumer__mutmut_3": 1,
                "my_lib.x_simple_consumer__mutmut_4": 1,
                "my_lib.x_simple_consumer__mutmut_5": 1,
                "my_lib.x_simple_consumer__mutmut_6": 0,
                "my_lib.x_simple_consumer__mutmut_7": 1,
                "my_lib.x_double_generator__mutmut_1": 1,
                "my_lib.x_double_generator__mutmut_2": 1,
                "my_lib.x_double_generator__mutmut_3": 0,
                "my_lib.x_double_generator__mutmut_4": 0,
                "my_lib.xǁPointǁ__init____mutmut_1": 1,
                "my_lib.xǁPointǁ__init____mutmut_2": 1,
                "my_lib.xǁPointǁabs__mutmut_1": 33,
                "my_lib.xǁPointǁabs__mutmut_2": 33,
                "my_lib.xǁPointǁabs__mutmut_3": 33,
                "my_lib.xǁPointǁabs__mutmut_4": 33,
                "my_lib.xǁPointǁabs__mutmut_5": 33,
                "my_lib.xǁPointǁabs__mutmut_6": 33,
                "my_lib.xǁPointǁadd__mutmut_1": 0,
                "my_lib.xǁPointǁadd__mutmut_2": 1,
                "my_lib.xǁPointǁadd__mutmut_3": 1,
                "my_lib.xǁPointǁadd__mutmut_4": 0,
                "my_lib.xǁPointǁto_origin__mutmut_1": 1,
                "my_lib.xǁPointǁto_origin__mutmut_2": 1,
                "my_lib.xǁPointǁto_origin__mutmut_3": 0,
                "my_lib.xǁPointǁto_origin__mutmut_4": 0,
                "my_lib.xǁPointǁ__len____mutmut_1": 33,
                "my_lib.xǁPointǁfrom_coords__mutmut_1": 1,
                "my_lib.xǁPointǁfrom_coords__mutmut_2": 0,
                "my_lib.xǁPointǁfrom_coords__mutmut_3": 1,
                "my_lib.xǁPointǁfrom_coords__mutmut_4": 1,
                "my_lib.xǁPointǁfrom_coords__mutmut_5": 1,
                "my_lib.xǁPointǁfrom_coords__mutmut_6": 1,
                "my_lib.xǁPointǁpragma_on_staticmethod_decorator__mutmut_1": 1,
                "my_lib.xǁPointǁpragma_on_staticmethod_decorator__mutmut_2": 1,
                "my_lib.xǁPointǁpragma_on_staticmethod_decorator__mutmut_3": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_1": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_2": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_3": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_4": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_5": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_6": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_7": 1,
                "my_lib.xǁPointǁpragma_on_classmethod_decorator__mutmut_8": 1,
                "my_lib.x_escape_sequences__mutmut_1": 1,
                "my_lib.x_escape_sequences__mutmut_2": 0,
                "my_lib.x_escape_sequences__mutmut_3": 1,
                "my_lib.x_escape_sequences__mutmut_4": 0,
                "my_lib.x_escape_sequences__mutmut_5": 0,
                "my_lib.x_create_a_segfault_when_mutated__mutmut_1": -11,
                "my_lib.x_create_a_segfault_when_mutated__mutmut_2": 0,
                "my_lib.x_create_a_segfault_when_mutated__mutmut_3": 0,
                "my_lib.x_some_func__mutmut_1": 0,
                "my_lib.x_some_func__mutmut_2": 0,
                "my_lib.x_some_func__mutmut_3": 1,
                "my_lib.x_func_with_star__mutmut_1": 1,
                "my_lib.x_func_with_star__mutmut_2": 1,
                "my_lib.x_func_with_star__mutmut_3": 1,
                "my_lib.x_func_with_arbitrary_args__mutmut_1": 1,
                "my_lib.xǁColorǁasync_get__mutmut_1": 1,
                "my_lib.xǁColorǁasync_get__mutmut_2": 0,
                "my_lib.xǁColorǁasync_get_all__mutmut_1": 1,
                "my_lib.xǁColorǁasync_get_all__mutmut_2": 0,
                "my_lib.xǁColorǁis_primary__mutmut_1": 1,
                "my_lib.xǁColorǁdarken__mutmut_1": 0,
                "my_lib.xǁColorǁdarken__mutmut_2": 1,
                "my_lib.xǁColorǁfrom_name__mutmut_1": 1,
                "my_lib.xǁ_PrivateClassǁget_question__mutmut_1": 0,
                "my_lib.xǁ_PrivateClassǁget_question__mutmut_2": 0,
                "my_lib.xǁ_PrivateClassǁget_question__mutmut_3": 0,
                "my_lib.xǁ_PrivateClassǁget_answer__mutmut_1": 0,
                "my_lib.x_divide__mutmut_1": 1,
                "my_lib.x_write_into_file__mutmut_1": 1,
                "my_lib.x_write_into_file__mutmut_2": 1,
                "my_lib.x_write_into_file__mutmut_3": 1,
                "my_lib.x_write_into_file__mutmut_4": 1,
                "my_lib.x_write_into_file__mutmut_5": 1,
                "my_lib.x_write_into_file__mutmut_6": 1,
                "my_lib.x_write_into_file__mutmut_7": 1,
                "my_lib.x_write_into_file__mutmut_8": 0,
                "my_lib.x_write_into_file__mutmut_9": 1,
                "my_lib.x_write_into_file__mutmut_10": 1,
            }
        }
    )


def test_rerun_with_every_verdict_cached_runs_no_tests(monkeypatch):
    """With nothing left to test, neither the clean run nor the forced-fail run is needed."""
    assert run_mutmut_on_project("my_lib")

    def no_tests_expected(self, *, mutant_name, tests):
        raise AssertionError(f"unexpected test run for mutant {mutant_name!r} with tests {tests!r}")

    monkeypatch.setattr(PytestRunner, "run_tests", no_tests_expected)

    with change_cwd(E2E_PROJECTS / "my_lib"):
        mutmut._reset_globals()
        _run([], None)
