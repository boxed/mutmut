import importlib
import os
import sys
from pathlib import Path

import coverage
import pytest

from mutmut.code_coverage import CoverageInfo
from mutmut.code_coverage import _excluded_lines
from mutmut.code_coverage import _gather_coverage_in_this_process
from mutmut.code_coverage import gather_coverage
from mutmut.code_coverage import get_excluded_lines_for_file


def test_get_excluded_lines_for_file_without_data():
    assert get_excluded_lines_for_file("foo.py", None) == set()


def test_get_excluded_lines_for_file_unknown_file():
    assert get_excluded_lines_for_file("foo.py", {}) == set()


def test_excluded_lines_of_unreadable_file(tmp_path):
    assert _excluded_lines(coverage.Coverage(data_file=None), str(tmp_path / "does_not_exist.py")) == set()


def test_excluded_lines_reports_only_the_first_line_of_each_statement(tmp_path):
    # coverage.py only reports the line a statement *starts* on, which is why the
    # excluded lines have to be expanded to full statements before they are of any use.
    # If that ever changes, the expansion is doing unnecessary work.
    source_file = tmp_path / "excluded.py"
    source_file.write_text(
        "def keep(a, b):\n"
        "    return (\n"
        "        a\n"
        "        + b\n"
        "    )\n"
        "\n"
        "def drop(a, b):  # pragma: no cover\n"
        "    return (\n"
        "        a\n"
        "        + b\n"
        "    )\n"
    )

    excluded = _excluded_lines(coverage.Coverage(data_file=None), str(source_file))

    assert excluded == {7, 8}


def test_excluded_lines_honours_the_projects_coverage_config(tmp_path, monkeypatch):
    (tmp_path / ".coveragerc").write_text("[report]\nexclude_also =\n    if not_tested:\n")
    source_file = tmp_path / "configured.py"
    source_file.write_text("def foo(not_tested):\n    if not_tested:\n        return 1 + 1\n    return 2 + 2\n")

    monkeypatch.chdir(tmp_path)
    excluded = _excluded_lines(coverage.Coverage(data_file=None), str(source_file))

    assert excluded == {2, 3}


class _RunnerThatImports:
    """Stands in for a TestRunner whose test run imports a dependency.

    The measurement only ever calls ``collect_main_test_coverage``, so this is
    enough to observe what the run leaves behind in ``sys.modules``.
    """

    def __init__(self, module_name: str) -> None:
        self.module_name = module_name

    def collect_main_test_coverage(self, cov: coverage.Coverage) -> int:
        importlib.import_module(self.module_name)
        return 0


def _minimal_project(tmp_path, monkeypatch) -> None:
    """chdir somewhere config() can load; importing isolation reads it at import time."""
    (tmp_path / "src").mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)


def _importable_module(tmp_path, monkeypatch, name: str) -> str:
    (tmp_path / f"{name}.py").write_text("value = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    _minimal_project(tmp_path, monkeypatch)
    return name


def test_the_measurement_leaves_the_modules_it_imported_loaded(tmp_path, monkeypatch):
    """Regression test for #528: the eviction that broke numpy and friends is gone."""
    name = _importable_module(tmp_path, monkeypatch, "imported_by_the_coverage_run")
    try:
        _gather_coverage_in_this_process(_RunnerThatImports(name), [])
        assert name in sys.modules
    finally:
        sys.modules.pop(name, None)


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestGatherCoverageIsolatesTheCaller:
    """The other half of #528: dropping the eviction is only safe if the imports never land here."""

    def test_results_come_back_but_imports_do_not(self, tmp_path, monkeypatch):
        name = _importable_module(tmp_path, monkeypatch, "imported_by_the_test_run")

        info = gather_coverage(_RunnerThatImports(name), [])

        assert isinstance(info, CoverageInfo)
        # The import the run did never reached this process.
        assert name not in sys.modules

    def test_measurements_cross_the_fork_boundary(self, tmp_path, monkeypatch):
        """A real file's covered and excluded lines survive the round trip."""
        _minimal_project(tmp_path, monkeypatch)
        (tmp_path / "mutants").mkdir()
        (tmp_path / "mutants" / "measured.py").write_text(
            "def covered():\n    return 1\n\ndef never_called():  # pragma: no cover\n    return 2\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path / "mutants"))

        class _RunnerThatRunsTheCode:
            def collect_main_test_coverage(self, cov: coverage.Coverage) -> int:
                with cov.collect():
                    import measured

                    measured.covered()
                return 0

        info = gather_coverage(_RunnerThatRunsTheCode(), [Path("measured.py")])

        key = str((tmp_path / "mutants" / "measured.py").absolute())
        # Both `def` lines run at import; only never_called's body (5) does not.
        assert info.covered_lines[key] == {1, 2, 4}
        # Not an exact match: which lines of an excluded statement get reported is a
        # coverage.py version detail. All this test needs is that they came back.
        assert 4 in info.excluded_lines[key]

    def test_child_failure_is_reported_to_the_caller(self, tmp_path, monkeypatch):
        """A measurement that blows up must not look like empty coverage."""
        _minimal_project(tmp_path, monkeypatch)

        class _RunnerThatFails:
            def collect_main_test_coverage(self, cov: coverage.Coverage) -> int:
                raise RuntimeError("conftest exploded")

        with pytest.raises(ChildProcessError, match="conftest exploded"):
            gather_coverage(_RunnerThatFails(), [])
