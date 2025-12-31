import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from nootnoot.cli import _run
from nootnoot.config import ensure_config_loaded
from nootnoot.meta import SourceFileMutationData
from nootnoot.mutation import walk_source_files
from nootnoot.state import NootNootState


@contextmanager
def change_cwd(path):
    old_cwd = Path(Path.cwd()).resolve()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def read_all_stats_for_project(project_path: Path, state: NootNootState) -> dict[str, dict]:
    """Create a single dict from all mutant results in *.meta files."""
    with change_cwd(project_path):
        ensure_config_loaded(state)

        stats = {}
        config = state.config
        debug = config.debug if config else False
        for p in walk_source_files(state):
            if config is not None and config.should_ignore_for_mutation(p):
                continue
            data = SourceFileMutationData(path=p)
            data.load(debug=debug)
            stats[str(data.meta_path)] = data.exit_code_by_key

        return stats


def read_json_file(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json_file(path: Path, data: Any) -> None:
    with Path(path).open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def asserts_results_did_not_change(project: str, state: NootNootState) -> None:
    """Run nootnoot on this project and verify that the results stay the same for all mutations."""
    project_path = Path("..").parent / "e2e_projects" / project

    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # nootnoot run
    with change_cwd(project_path):
        _run(state, [], None)

    results = read_all_stats_for_project(project_path, state)

    snapshot_path = Path("tests") / "e2e" / "snapshots" / (project + ".json")

    if snapshot_path.exists():
        # compare results against previous snapshot
        previous_snapshot = read_json_file(snapshot_path)

        err_msg = (
            f"NootNoot results changed for the E2E project '{project}'. "
            f"If this change was on purpose, delete {snapshot_path} and rerun the tests."
        )
        assert results == previous_snapshot, err_msg
    else:
        # create the first snapshot
        write_json_file(snapshot_path, results)


def test_my_lib_result_snapshot(nootnoot_state):
    asserts_results_did_not_change("my_lib", nootnoot_state)


def test_config_result_snapshot(nootnoot_state):
    asserts_results_did_not_change("config", nootnoot_state)


def test_mutate_only_covered_lines_result_snapshot(nootnoot_state):
    asserts_results_did_not_change("mutate_only_covered_lines", nootnoot_state)
