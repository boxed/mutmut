"""Tests for the incremental-stats bookkeeping in ``ListAllTestsResult``."""

import json
from collections import defaultdict
from pathlib import Path

import pytest

from mutmut.runners.harness import ListAllTestsResult
from mutmut.state import state

STATS_FILE = Path("mutants/mutmut-stats.json")


@pytest.fixture(autouse=True)
def isolated_stats(tmp_path, monkeypatch):
    # save_stats() writes mutants/mutmut-stats.json relative to the cwd, and it
    # loads the config on the way, which needs a guessable source dir to exist.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mutants").mkdir()
    (tmp_path / "src").mkdir()
    saved = state().tests_by_mangled_function_name
    state().tests_by_mangled_function_name = defaultdict(set)
    yield
    state().tests_by_mangled_function_name = saved


class TestClearOutObsoleteTestNames:
    def test_obsolete_test_names_are_dropped_and_persisted(self, capsys):
        state().tests_by_mangled_function_name["pkg.foo.x_add"] |= {
            "tests/test_foo.py::test_add",
            "tests/test_gone.py::test_add",
        }
        state().tests_by_mangled_function_name["pkg.foo.x_sub"].add("tests/test_gone.py::test_sub")

        ListAllTestsResult(ids={"tests/test_foo.py::test_add"}).clear_out_obsolete_test_names()

        assert dict(state().tests_by_mangled_function_name) == {
            "pkg.foo.x_add": {"tests/test_foo.py::test_add"},
            "pkg.foo.x_sub": set(),
        }
        assert "Removed 2 obsolete test names" in capsys.readouterr().out
        on_disk = json.loads(STATS_FILE.read_text())
        assert on_disk["tests_by_mangled_function_name"] == {
            "pkg.foo.x_add": ["tests/test_foo.py::test_add"],
            "pkg.foo.x_sub": [],
        }

    def test_nothing_obsolete_leaves_stats_file_untouched(self, capsys):
        state().tests_by_mangled_function_name["pkg.foo.x_add"].add("tests/test_foo.py::test_add")

        ListAllTestsResult(ids={"tests/test_foo.py::test_add"}).clear_out_obsolete_test_names()

        assert dict(state().tests_by_mangled_function_name) == {"pkg.foo.x_add": {"tests/test_foo.py::test_add"}}
        assert capsys.readouterr().out == ""
        assert not STATS_FILE.exists()
