"""collect_or_load_stats end to end: an edited test file between two runs (#635)."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from mutmut.__main__ import collect_or_load_stats
from mutmut.__main__ import compute_test_file_hashes
from mutmut.mutation.data import SourceFileMutationData
from mutmut.runners.harness import ListAllTestsResult
from mutmut.state import reset_state
from mutmut.state import state
from mutmut.stats import save_stats
from mutmut.workers.isolation import MutantRunner

TEST_FOO = "tests/test_a.py::test_foo"
TEST_BAR = "tests/test_b.py::test_bar"
FOO = "mymod.x_foo"
BAR = "mymod.x_bar"
FUNCTION_HASHES = {FOO: "foo-hash", BAR: "bar-hash"}


@pytest.fixture(autouse=True)
def fresh_state():
    reset_state()
    yield
    reset_state()


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project after a full run: both mutants killed, by tests in separate files."""
    monkeypatch.chdir(tmp_path)
    Path("pyproject.toml").write_text('[tool.mutmut]\nsource_paths = ["src"]\n')
    Path("src").mkdir()
    Path("src/mymod.py").write_text("def foo():\n    return 1\n\n\ndef bar():\n    return 2\n")
    Path("tests").mkdir()
    Path("tests/test_a.py").write_text("def test_foo(): pass\n")
    Path("tests/test_b.py").write_text("def test_bar(): pass\n")
    Path("mutants/src").mkdir(parents=True)

    state().current_function_hashes = dict(FUNCTION_HASHES)
    state().tests_by_mangled_function_name[FOO] = {TEST_FOO}
    state().tests_by_mangled_function_name[BAR] = {TEST_BAR}
    state().duration_by_test.update({TEST_FOO: 0.01, TEST_BAR: 0.01})
    state().test_file_hashes = compute_test_file_hashes([TEST_FOO, TEST_BAR])
    save_stats()

    data = SourceFileMutationData(path=Path("src/mymod.py"))
    data.exit_code_by_key = {f"{FOO}__mutmut_1": 1, f"{BAR}__mutmut_1": 1}
    data.save()


def _incremental_run() -> Mock:
    """Start a new run with unchanged source, the way `mutmut run` does after mutant generation."""
    reset_state()
    state().current_function_hashes = dict(FUNCTION_HASHES)
    runner = Mock(spec=MutantRunner)
    runner.list_all_tests.return_value = ListAllTestsResult(ids={TEST_FOO, TEST_BAR})

    def collect_stats(tests):
        for test in tests:
            state().duration_by_test[test] = 0.01
        if TEST_FOO in tests:
            state().tests_by_mangled_function_name[FOO].add(TEST_FOO)
        return 0

    runner.collect_stats.side_effect = collect_stats
    collect_or_load_stats(runner)
    return runner


def _results() -> dict[str, int | None]:
    data = SourceFileMutationData(path=Path("src/mymod.py"))
    data.load()
    return data.exit_code_by_key


@pytest.mark.usefixtures("project")
def test_unchanged_test_files_keep_stats_and_results():
    runner = _incremental_run()

    runner.collect_stats.assert_not_called()
    assert _results() == {f"{FOO}__mutmut_1": 1, f"{BAR}__mutmut_1": 1}


@pytest.mark.usefixtures("project")
def test_edited_test_file_is_recollected_and_its_verdicts_reset():
    Path("tests/test_a.py").write_text("def test_foo(): assert False\n")

    runner = _incremental_run()

    runner.collect_stats.assert_called_once_with({TEST_FOO})
    assert _results() == {f"{FOO}__mutmut_1": None, f"{BAR}__mutmut_1": 1}
    assert state().tests_by_mangled_function_name[FOO] == {TEST_FOO}

    # the new baseline is saved, so the next run sees nothing changed
    runner = _incremental_run()

    runner.collect_stats.assert_not_called()
