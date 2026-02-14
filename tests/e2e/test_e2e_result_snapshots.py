import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any
import pytest
import sys

import mutmut
from mutmut.__main__ import SourceFileMutationData, _run, ensure_config_loaded, walk_source_files


@contextmanager
def change_cwd(path):
    old_cwd = Path(Path.cwd()).resolve()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def read_all_stats_for_project(project_path: Path) -> dict[str, dict]:
    """Create a single dict from all mutant results in *.meta files"""
    with change_cwd(project_path):
        ensure_config_loaded()

        stats = {}
        for p in walk_source_files():
            if mutmut.config.should_ignore_for_mutation(p):  # type: ignore
                continue
            data = SourceFileMutationData(path=p)
            data.load()
            stats[str(data.meta_path)] = data.exit_code_by_key

        return stats


def read_json_file(path: Path):
    with open(path, 'r') as file:
        return json.load(file)


def write_json_file(path: Path, data: Any):
    with open(path, 'w') as file:
        json.dump(data, file, indent=2)


def asserts_results_did_not_change(project: str):
    """Runs mutmut on this project and verifies that the results stay the same for all mutations."""
    project_path = Path("..").parent / "e2e_projects" / project

    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # mutmut run
    with change_cwd(project_path):
        _run([], None)

    results = read_all_stats_for_project(project_path)

    snapshot_path = Path("tests") / "e2e" / "snapshots" / (project + ".json")

    if snapshot_path.exists():
        # compare results against previous snapshot
        previous_snapshot = read_json_file(snapshot_path)

        err_msg = f'Mutmut results changed for the E2E project \'{project}\'. If this change was on purpose, delete {snapshot_path} and rerun the tests.'
        assert results == previous_snapshot, err_msg
    else:
        # create the first snapshot
        write_json_file(snapshot_path, results)


def test_my_lib_result_snapshot():
    mutmut._reset_globals()
    asserts_results_did_not_change("my_lib")


def test_config_result_snapshot():
    mutmut._reset_globals()
    asserts_results_did_not_change("config")


def test_mutate_only_covered_lines_result_snapshot():
    mutmut._reset_globals()
    asserts_results_did_not_change("mutate_only_covered_lines")


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Can only test python 3.14 features on 3.14")
def test_python_3_14_result_snapshot():
    mutmut._reset_globals()
    asserts_results_did_not_change("py3_14_features")


def test_type_checking_result_snapshot():
    mutmut._reset_globals()
    asserts_results_did_not_change("type_checking")
