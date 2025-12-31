import json
import warnings
from pathlib import Path

from nootnoot.config import Config
from nootnoot.meta import SourceFileMutationData
from nootnoot.persistence import SCHEMA_VERSION, load_stats, save_stats
from nootnoot.state import NootNootState


def make_state(*, debug: bool) -> NootNootState:
    state = NootNootState()
    state.config = Config(
        also_copy=[],
        do_not_mutate=[],
        max_stack_depth=-1,
        debug=debug,
        paths_to_mutate=[Path("src")],
        pytest_add_cli_args=[],
        pytest_add_cli_args_test_selection=[],
        tests_dir=[],
        mutate_only_covered_lines=False,
    )
    return state


def test_stats_roundtrip_with_schema_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("mutants").mkdir()
    state = make_state(debug=False)
    state.duration_by_test["tests/test_a.py::test_a"] = 1.25
    state.tests_by_mangled_function_name["pkg.mod.x__nootnoot_1"] = {"tests/test_a.py::test_a"}
    state.stats_time = 9.5

    save_stats(state)

    raw = json.loads(Path("mutants/nootnoot-stats.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION

    reloaded = make_state(debug=False)
    assert load_stats(reloaded) is True
    assert reloaded.duration_by_test["tests/test_a.py::test_a"] == 1.25
    assert reloaded.tests_by_mangled_function_name["pkg.mod.x__nootnoot_1"] == {"tests/test_a.py::test_a"}
    assert reloaded.stats_time == 9.5


def test_stats_unknown_keys_warns_in_debug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("mutants").mkdir()

    payload = {
        "schema_version": SCHEMA_VERSION,
        "tests_by_mangled_function_name": {"pkg.mod.x__nootnoot_1": ["t"]},
        "duration_by_test": {"t": 0.1},
        "stats_time": 0.0,
        "extra": "value",
    }
    Path("mutants/nootnoot-stats.json").write_text(
        json.dumps(payload, indent=4),
        encoding="utf-8",
    )

    state = make_state(debug=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert load_stats(state) is True

    assert any("unexpected keys" in str(item.message) for item in caught)


def test_meta_roundtrip_with_schema_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("mutants/src").mkdir(parents=True)
    source_path = Path("src/example.py")

    source_data = SourceFileMutationData(path=source_path)
    source_data.exit_code_by_key = {"pkg.mod.x__nootnoot_1": 0}
    source_data.durations_by_key = {"pkg.mod.x__nootnoot_1": 0.4}
    source_data.estimated_time_of_tests_by_mutant = {"pkg.mod.x__nootnoot_1": 1.2}
    source_data.save()

    raw = json.loads(Path("mutants/src/example.py.meta").read_text(encoding="utf-8"))
    assert raw["schema_version"] == SCHEMA_VERSION

    reloaded = SourceFileMutationData(path=source_path)
    reloaded.load()
    assert reloaded.exit_code_by_key == source_data.exit_code_by_key
    assert reloaded.durations_by_key == source_data.durations_by_key
    assert reloaded.estimated_time_of_tests_by_mutant == source_data.estimated_time_of_tests_by_mutant


def test_meta_unknown_keys_warns_in_debug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("mutants/src").mkdir(parents=True)
    source_path = Path("src/example.py")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "exit_code_by_key": {"pkg.mod.x__nootnoot_1": 0},
        "durations_by_key": {"pkg.mod.x__nootnoot_1": 0.4},
        "estimated_durations_by_key": {"pkg.mod.x__nootnoot_1": 1.2},
        "extra": "value",
    }
    Path("mutants/src/example.py.meta").write_text(
        json.dumps(payload, indent=4),
        encoding="utf-8",
    )

    source_data = SourceFileMutationData(path=source_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        source_data.load(debug=True)

    assert any("unexpected keys" in str(item.message) for item in caught)
