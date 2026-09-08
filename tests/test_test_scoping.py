"""Scoping the clean and forced-fail runs to the mutants that will be tested."""

from unittest.mock import Mock

import pytest

import mutmut.__main__
from mutmut.__main__ import clean_run_test_selection
from mutmut.__main__ import collect_or_load_stats
from mutmut.__main__ import probe_tests_for_forced_fail
from mutmut.__main__ import tests_for_mutants as relevant_tests_for
from mutmut.runners.harness import ListAllTestsResult
from mutmut.state import reset_state
from mutmut.state import state


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()
    yield
    reset_state()


def _associate(function: str, *tests: str, duration: float = 0.01) -> None:
    for test in tests:
        state().tests_by_mangled_function_name[function].add(test)
        state().duration_by_test.setdefault(test, duration)


class TestTestsForMutants:
    def test_unions_the_tests_of_the_mutants_functions(self):
        _associate("pkg.mod.x_f", "tests/test_a.py::test_one", "tests/test_a.py::test_two")
        _associate("pkg.mod.x_g", "tests/test_b.py::test_three")
        mutants = [
            (None, "pkg.mod.x_f__mutmut_1", None),
            (None, "pkg.mod.x_f__mutmut_2", None),
            (None, "pkg.mod.x_g__mutmut_1", None),
        ]

        assert relevant_tests_for(mutants) == {  # type: ignore[arg-type]
            "tests/test_a.py::test_one",
            "tests/test_a.py::test_two",
            "tests/test_b.py::test_three",
        }

    def test_mutants_in_a_package_init_are_looked_up_by_the_package_name(self):
        _associate("pkg.x_f", "tests/test_a.py::test_one")

        assert relevant_tests_for([(None, "pkg.__init__.x_f__mutmut_1", None)]) == {"tests/test_a.py::test_one"}  # type: ignore[list-item]

    def test_unknown_functions_have_no_tests(self):
        assert relevant_tests_for([(None, "pkg.mod.x_unknown__mutmut_1", None)]) == set()  # type: ignore[list-item]


class TestCleanRunTestSelection:
    def test_lists_the_relevant_tests_when_they_are_a_minority(self):
        for i in range(10):
            state().duration_by_test[f"tests/test_a.py::test_{i}"] = 0.01

        assert clean_run_test_selection({"tests/test_a.py::test_3", "tests/test_a.py::test_1"}) == [
            "tests/test_a.py::test_1",
            "tests/test_a.py::test_3",
        ]

    def test_runs_the_configured_selection_once_most_tests_are_relevant(self):
        for i in range(10):
            state().duration_by_test[f"tests/test_a.py::test_{i}"] = 0.01

        assert clean_run_test_selection({f"tests/test_a.py::test_{i}" for i in range(5)}) == []


class TestProbeTestsForForcedFail:
    def test_prefers_tests_that_reach_many_functions_from_different_files(self):
        _associate(
            "pkg.mod.x_a", "tests/test_a.py::test_broad", "tests/test_a.py::test_narrow", "tests/test_b.py::test_b"
        )
        _associate("pkg.mod.x_b", "tests/test_a.py::test_broad", "tests/test_b.py::test_b")
        _associate("pkg.mod.x_c", "tests/test_a.py::test_broad")
        _associate("pkg.mod.x_d", "tests/test_c.py::test_c")
        tests = relevant_tests_for(
            [(None, f"pkg.mod.x_{f}__mutmut_1", None) for f in "abcd"]  # type: ignore[misc]
        )

        assert probe_tests_for_forced_fail(tests) == [
            "tests/test_a.py::test_broad",
            "tests/test_b.py::test_b",
            "tests/test_c.py::test_c",
        ]

    def test_is_limited_to_a_few_probes(self):
        for i in range(6):
            _associate("pkg.mod.x_a", f"tests/test_{i}.py::test")

        assert len(probe_tests_for_forced_fail(state().tests_by_mangled_function_name["pkg.mod.x_a"], limit=3)) == 3

    def test_means_everything_when_no_test_has_stats(self):
        assert probe_tests_for_forced_fail({"tests/test_a.py::test_unknown"}) == []


class TestCollectOrLoadStats:
    def test_reports_a_full_collection(self, monkeypatch):
        monkeypatch.setattr(mutmut.__main__, "load_stats", lambda: False)
        monkeypatch.setattr(mutmut.__main__, "_refresh_change_detection_baseline", lambda: None)
        collected = Mock()
        monkeypatch.setattr(mutmut.__main__, "run_stats_collection", collected)

        assert collect_or_load_stats(Mock()) is True
        collected.assert_called_once()

    def test_reports_loaded_stats(self, monkeypatch):
        monkeypatch.setattr(mutmut.__main__, "load_stats", lambda: True)
        monkeypatch.setattr(mutmut.__main__, "save_stats", lambda: None)
        state().duration_by_test["tests/test_a.py::test_one"] = 0.01
        runner = Mock()
        runner.list_all_tests.return_value = ListAllTestsResult(ids={"tests/test_a.py::test_one"})

        assert collect_or_load_stats(runner) is False
