"""Tests for the test-to-mutant association sanity check."""

from collections import defaultdict
from pathlib import Path

import pytest

import mutmut
from mutmut.__main__ import _check_test_to_mutant_associations
from mutmut.mutation.data import SourceFileMutationData


@pytest.fixture(autouse=True)
def reset_tests_by_mangled_function_name():
    saved = mutmut.tests_by_mangled_function_name
    mutmut.tests_by_mangled_function_name = defaultdict(set)
    yield
    mutmut.tests_by_mangled_function_name = saved


def _make_sfmd(mutant_names_per_path: dict[str, list[str]]) -> dict[str, SourceFileMutationData]:
    """Build a fake source_file_mutation_data_by_path mapping."""
    result: dict[str, SourceFileMutationData] = {}
    for path_str, mutant_names in mutant_names_per_path.items():
        m = SourceFileMutationData(path=Path(path_str))
        m.exit_code_by_key = dict.fromkeys(mutant_names)
        result[path_str] = m
    return result


class TestCheckTestToMutantAssociations:
    def test_no_recorded_keys_is_noop(self):
        # When stats recorded nothing, the existing zero-check elsewhere
        # surfaces it. This function should not duplicate that work.
        sfmd = _make_sfmd({"pkg/foo.py": ["pkg.foo.x_add__mutmut_1"]})
        _check_test_to_mutant_associations(sfmd)  # must not exit

    def test_overlapping_keys_is_noop(self):
        # Healthy case: recorded key matches a mutant lookup key.
        mutmut.tests_by_mangled_function_name["pkg.foo.x_add"].add("tests/test_foo.py::test_add")
        sfmd = _make_sfmd({"pkg/foo.py": ["pkg.foo.x_add__mutmut_1"]})
        _check_test_to_mutant_associations(sfmd)  # must not exit

    def test_no_expected_keys_is_noop(self):
        # No mutants generated yet -> nothing to compare against.
        mutmut.tests_by_mangled_function_name["whatever.x_add"].add("tests/test_foo.py::test_add")
        _check_test_to_mutant_associations({})  # must not exit

    def test_disjoint_keys_exits_with_diagnostic(self, capsys):
        # The bug case: trampolines were hit but recorded under a key shape
        # (no path prefix) that no mutant lookup can ever match.
        mutmut.tests_by_mangled_function_name["foo.x_add"].add("tests/test_foo.py::test_add")
        mutmut.tests_by_mangled_function_name["foo.x_is_positive"].add("tests/test_foo.py::test_is_positive")
        sfmd = _make_sfmd({"pkg/foo.py": ["pkg.foo.x_add__mutmut_1", "pkg.foo.x_is_positive__mutmut_1"]})

        with pytest.raises(SystemExit) as exc_info:
            _check_test_to_mutant_associations(sfmd)

        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "tests recorded trampoline hits but none match any mutant key" in out
        assert "pythonpath" in out
        assert "Recorded keys" in out and "foo.x_add" in out
        assert "Expected keys" in out and "pkg.foo.x_add" in out

    def test_partial_overlap_is_noop(self):
        # Even if only a subset matches, we don't bail - the per-mutant
        # lookups for unmatched ones will simply yield "No Tests" which is
        # legitimate (e.g. uncovered code).
        mutmut.tests_by_mangled_function_name["pkg.foo.x_add"].add("tests/test_foo.py::test_add")
        sfmd = _make_sfmd({"pkg/foo.py": ["pkg.foo.x_add__mutmut_1", "pkg.foo.x_uncovered__mutmut_1"]})
        _check_test_to_mutant_associations(sfmd)  # must not exit
