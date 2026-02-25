import shutil
from pathlib import Path

from tests.e2e.e2e_utils import change_cwd, read_all_stats_for_project, write_json_file, read_json_file

import mutmut
from mutmut.__main__ import _run


def test_rerun_preserves_cached_results():
    """Rerunning mutmut on unchanged source must not reset cached exit codes to None.

    Strategy: run mutmut once, then inject a sentinel exit code (99) into the
    meta file. If the second run preserves the cache, the sentinel survives.
    If it resets and re-tests, 99 gets replaced with a real exit code.
    """
    project_path = Path("..").parent / "e2e_projects" / "my_lib"
    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # First run: generate and test all mutants
    mutmut._reset_globals()
    with change_cwd(project_path):
        _run([], None)

    # Inject sentinel exit code (99) into every mutant result
    meta_files = list(mutants_path.rglob("*.meta"))
    assert meta_files, "Expected .meta files after first run"

    sentinel = 99
    for meta_file in meta_files:
        meta = read_json_file(meta_file)
        for key in meta["exit_code_by_key"]:
            meta["exit_code_by_key"][key] = sentinel
        write_json_file(meta_file, meta)

    # Second run: source unchanged, sentinel values should survive
    mutmut._reset_globals()
    with change_cwd(project_path):
        _run([], None)

    second_run_stats = read_all_stats_for_project(project_path)

    # Every result should still be the sentinel — not None, not a real exit code
    for meta_path, results in second_run_stats.items():
        for mutant_name, exit_code in results.items():
            assert exit_code == sentinel, (
                f"Cached result for {mutant_name} in {meta_path} was not preserved. "
                f"Expected sentinel {sentinel}, got {exit_code}."
            )

    # Cleanup
    shutil.rmtree(mutants_path, ignore_errors=True)
