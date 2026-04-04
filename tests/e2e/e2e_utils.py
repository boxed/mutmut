import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import mutmut
from mutmut.__main__ import SourceFileMutationData
from mutmut.__main__ import _run
from mutmut.__main__ import walk_source_files
from mutmut.configuration import Config


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
        Config.reset()
        Config.ensure_loaded()

        stats = {}
        for p in walk_source_files():
            if Config.get().should_ignore_for_mutation(p):
                continue
            data = SourceFileMutationData(path=p)
            data.load()
            stats[str(data.meta_path)] = data.exit_code_by_key

        return stats


def read_json_file(path: Path):
    with open(path) as file:
        return json.load(file)


def write_json_file(path: Path, data: Any):
    with open(path, "w") as file:
        json.dump(data, file, indent=2)
        file.write("\n")  # ensure newline at end of file for POSIX compliance


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
E2E_PROJECTS = REPO_ROOT / "e2e_projects"


def run_mutmut_on_project(project: str) -> dict:
    """Runs mutmut on this project and verifies that the results stay the same for all mutations."""
    mutmut._reset_globals()

    project_path = E2E_PROJECTS / project

    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # mutmut run
    with change_cwd(project_path):
        mutmut._reset_globals()
        _run([], None)

    return read_all_stats_for_project(project_path)
