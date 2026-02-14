import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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


def run_mutmut_on_project(project: str) -> dict:
    """Runs mutmut on this project and verifies that the results stay the same for all mutations."""
    mutmut._reset_globals()

    project_path = Path("..").parent / "e2e_projects" / project

    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # mutmut run
    with change_cwd(project_path):
        _run([], None)

    return read_all_stats_for_project(project_path)
