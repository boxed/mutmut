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


def asserts_handled_mutant_spec(project: str, filter_mutants: str):
    """Runs mutmut on this project and verifies that it was able to handle the supplied mutant spec."""
    project_path = Path("..").parent / "e2e_projects" / project

    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # mutmut run
    no_exception = True
    exception_type = None
    try:
        with change_cwd(project_path):
            mut_names = tuple([filter_mutants])
            _run(mut_names, None)
    except Exception as e:
        no_exception = False
        exception_type = e

    assert no_exception, str(exception_type)


def asserts_handled_mutant_spec_extra(project: str, tuple_first: str, filter_mutants: str):
    """Runs mutmut on this project and verifies that it was able to handle the supplied mutant spec."""
    project_path = Path("..").parent / "e2e_projects" / project

    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    # Work out a lower bound on the number of mutants that _should_ have run
    min_count = 2 + tuple_first.count(' ') + filter_mutants.count(' ')

    # mutmut run
    no_exception = True
    exception_type = None
    try:
        with change_cwd(project_path):
            mut_names = tuple([tuple_first, filter_mutants])
            _run(mut_names, None)
    except Exception as e:
        no_exception = False
        exception_type = e

    assert no_exception, str(exception_type)

    results = read_all_stats_for_project(project_path)
    actual_count = 0
    for item in results:
        matches = [1 for v in list(results[item].values()) if isinstance(v, int) and 33 != v]
        actual_count += sum(matches)

    assert actual_count >= min_count,\
        f"Test config expected at least {min_count} mutants run, only {actual_count} mutant was/were run"


def test_config_result_filter_singleton_mutant_explicit():
    mutmut._reset_globals()
    asserts_handled_mutant_spec("config", "config_pkg.math.x_add__mutmut_1")


def test_config_result_filter_singleton_mutant_wildcard():
    mutmut._reset_globals()
    asserts_handled_mutant_spec("config", "config_pkg.math.x_call_depth_two__mutmut_?")


def test_config_result_filter_doubleton_mutant_explicit():
    mutmut._reset_globals()
    asserts_handled_mutant_spec("config", "config_pkg.math.x_call_depth_two__mutmut_1 config_pkg.math.x_add__mutmut_1")


def test_config_result_filter_doubleton_mutant_wildcard():
    mutmut._reset_globals()
    asserts_handled_mutant_spec("config", "config_pkg.math.x_call_depth_two__mutmut_? config_pkg.math.x_add__mutmut_?")


def test_config_result_filter_tuple_plus_doubleton():
    mutmut._reset_globals()
    asserts_handled_mutant_spec_extra(
        'config',
        'config_pkg.x_hello__mutmut_1', 'config_pkg.math.x_call_depth_two__mutmut_? config_pkg.math.x_add__mutmut_?'
    )
