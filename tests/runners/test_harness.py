"""Tests for the incremental-stats bookkeeping in ``ListAllTestsResult``."""

import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from mutmut.runners.harness import ListAllTestsResult
from mutmut.runners.harness import PytestRunner
from mutmut.state import state

STATS_FILE = Path("mutants/mutmut-stats.json")


@pytest.fixture(autouse=True)
def isolated_stats(tmp_path, monkeypatch):
    # save_stats() writes mutants/mutmut-stats.json relative to the cwd, and it
    # loads the config on the way, which needs a guessable source dir to exist.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mutants").mkdir()
    (tmp_path / "src").mkdir()
    saved_tests = state().tests_by_mangled_function_name
    saved_durations = state().duration_by_test
    state().tests_by_mangled_function_name = defaultdict(set)
    state().duration_by_test = defaultdict(float)
    yield
    state().tests_by_mangled_function_name = saved_tests
    state().duration_by_test = saved_durations


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

    def test_obsolete_test_durations_are_dropped_and_persisted(self, capsys):
        state().tests_by_mangled_function_name["pkg.foo.x_add"].add("tests/test_foo.py::test_add")
        state().duration_by_test["tests/test_foo.py::test_add"] = 0.1
        state().duration_by_test["tests/test_gone.py::test_add"] = 0.2

        ListAllTestsResult(ids={"tests/test_foo.py::test_add"}).clear_out_obsolete_test_names()

        assert dict(state().duration_by_test) == {"tests/test_foo.py::test_add": 0.1}
        assert "Removed 1 obsolete test names" in capsys.readouterr().out
        on_disk = json.loads(STATS_FILE.read_text())
        assert on_disk["duration_by_test"] == {"tests/test_foo.py::test_add": 0.1}

    def test_nothing_obsolete_leaves_stats_file_untouched(self, capsys):
        state().tests_by_mangled_function_name["pkg.foo.x_add"].add("tests/test_foo.py::test_add")

        ListAllTestsResult(ids={"tests/test_foo.py::test_add"}).clear_out_obsolete_test_names()

        assert dict(state().tests_by_mangled_function_name) == {"pkg.foo.x_add": {"tests/test_foo.py::test_add"}}
        assert capsys.readouterr().out == ""
        assert not STATS_FILE.exists()


class TestStatsCollectorCollectionHits:
    def test_hits_recorded_during_collection_are_not_credited_to_the_first_test(self, monkeypatch):
        captured = []

        def fake_execute_pytest(self, params, **kwargs):
            captured.extend(kwargs["plugins"])
            return 0

        monkeypatch.setattr(PytestRunner, "execute_pytest", fake_execute_pytest)
        state()._stats.clear()

        PytestRunner().run_stats(tests=[])
        (collector,) = captured

        # Importing a module during collection calls a trampolined function.
        state()._stats.add("pkg.mod.x_table")
        collector.pytest_collection_finish(None)

        # Only hits recorded while the test runs belong to it.
        item = SimpleNamespace(nodeid="tests/test_mod.py::test_first")
        collector.pytest_runtest_logstart(item.nodeid, location=None)
        state()._stats.add("pkg.mod.x_double")
        collector.pytest_runtest_teardown(item, None)

        assert dict(state().tests_by_mangled_function_name) == {
            "pkg.mod.x_double": {"tests/test_mod.py::test_first"},
        }
        assert state()._stats == set()


class TestPreloadModuleNames:
    @staticmethod
    def _config(preload_modules, preload_modules_file):
        from types import SimpleNamespace

        return SimpleNamespace(preload_modules=preload_modules, preload_modules_file=preload_modules_file)

    def test_list_only(self):
        from mutmut.runners.harness import _preload_module_names

        assert _preload_module_names(self._config(["json", "decimal"], None)) == ["json", "decimal"]

    def test_file_only_skips_blank_lines_and_comments(self, tmp_path):
        from mutmut.runners.harness import _preload_module_names

        preload = tmp_path / "preload.txt"
        preload.write_text("# heavy imports\njson\n\n  decimal  \n")
        assert _preload_module_names(self._config([], str(preload))) == ["json", "decimal"]

    def test_list_comes_before_file(self, tmp_path):
        from mutmut.runners.harness import _preload_module_names

        preload = tmp_path / "preload.txt"
        preload.write_text("decimal\n")
        assert _preload_module_names(self._config(["json"], str(preload))) == ["json", "decimal"]

    def test_nothing_configured(self):
        from mutmut.runners.harness import _preload_module_names

        assert _preload_module_names(self._config([], None)) == []


def test_import_warmup_imports_listed_modules_and_skips_failures(patch_config, monkeypatch):
    from mutmut.configuration import ForkServerWarmup
    from mutmut.runners import harness

    imported = []

    def fake_import(name):
        imported.append(name)
        if name == "missing_module":
            raise ImportError(name)

    patch_config("forkserver_warmup", ForkServerWarmup.IMPORT)
    patch_config("preload_modules", ["json", "missing_module", "decimal"])
    patch_config("preload_modules_file", None)
    monkeypatch.setattr(harness.importlib, "import_module", fake_import)
    harness.PytestRunner().warm_up()
    assert imported == ["json", "missing_module", "decimal"]
