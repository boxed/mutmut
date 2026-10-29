from pathlib import Path
from unittest.mock import Mock

import pytest

from mutmut.__main__ import collect_or_load_stats
from mutmut.mutation.data import SourceFileMutationData
from mutmut.runners.harness import ListAllTestsResult
from mutmut.state import reset_state
from mutmut.state import state
from mutmut.stats import save_stats
from mutmut.workers.isolation import MutantRunner


@pytest.fixture(autouse=True)
def fresh_state():
    reset_state()
    yield
    reset_state()


@pytest.mark.parametrize(
    ("change", "tracking", "expected_total", "expected_double"),
    [
        ("callee", True, None, None),
        ("deleted_callee", True, None, None),
        ("caller", True, None, None),
        ("unchanged", True, 1, 0),
        ("callee", False, 1, 0),
    ],
)
def test_incremental_run_invalidates_cached_callers(
    tmp_path, monkeypatch, patch_config, change, tracking, expected_total, expected_double
):
    monkeypatch.chdir(tmp_path)
    Path("calc").mkdir()
    Path("calc/chain.py").touch()
    Path("pyproject.toml").write_text('[tool.mutmut]\nsource_paths = ["calc"]\n')
    patch_config("track_dependencies", tracking)

    add = "calc.ops.x_add"
    total = "calc.chain.x_total"
    double = "calc.chain.x_double_total"
    old_hashes = {add: "old", total: "same", double: "same", "calc.chain.x_total_extra": "same"}
    state().current_function_hashes = old_hashes.copy()
    state().function_dependencies[add] = {total}
    state().function_dependencies[total] = {double}
    # A recursive call graph must terminate and invalidate each caller once.
    state().function_dependencies[double] = {total}
    test_name = "tests/test_calc.py::test_total"
    state().duration_by_test[test_name] = 0.01
    state().tests_by_mangled_function_name[total] = {test_name}
    Path("mutants/calc").mkdir(parents=True)
    save_stats()

    data = SourceFileMutationData(path=Path("calc/chain.py"))
    total_key = f"{total}__mutmut_1"
    double_key = f"{double}__mutmut_1"
    unrelated_key = "calc.chain.x_total_extra__mutmut_1"
    unchecked_key = f"{total}__mutmut_2"
    data.exit_code_by_key = {total_key: 1, double_key: 0, unrelated_key: 37, unchecked_key: None}
    if change == "caller":
        # Mutant generation already resets the changed function itself.
        data.exit_code_by_key[total_key] = None
    data.save()
    before = data.meta_path.read_bytes()

    # Start the incremental stats phase with newly generated source hashes,
    # loading the dependency graph and verdicts from the previous run.
    reset_state()
    state().current_function_hashes = old_hashes.copy()
    if change == "callee":
        state().current_function_hashes[add] = "new"
    elif change == "deleted_callee":
        del state().current_function_hashes[add]
    elif change == "caller":
        state().current_function_hashes[total] = "new"
    runner = Mock(spec=MutantRunner)
    runner.list_all_tests.return_value = ListAllTestsResult(ids={test_name})

    def collect_stats(tests):
        state().duration_by_test[test_name] = 0.01
        state().tests_by_mangled_function_name[total] = {test_name}
        return 0

    runner.collect_stats.side_effect = collect_stats

    collect_or_load_stats(runner)

    data.load()
    assert data.exit_code_by_key == {
        total_key: expected_total,
        double_key: expected_double,
        unrelated_key: 37,
        unchecked_key: None,
    }
    if change == "unchanged" or not tracking:
        runner.collect_stats.assert_not_called()
        assert data.meta_path.read_bytes() == before
    else:
        runner.collect_stats.assert_called_once_with([])
    if change == "deleted_callee":
        assert add not in state().function_dependencies
