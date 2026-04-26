from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

from coverage import Coverage
from coverage import CoverageData

from mutmut.runners.harness import TestRunner


def get_covered_lines_for_file(filename: str, covered_lines: dict[str, set[int]]) -> set[int] | None:
    """Return covered lines for a file, or None if coverage filtering is not active.

    An empty dict means coverage is not enabled (mutate everything).
    A populated dict means only mutate covered lines."""
    if not covered_lines or filename is None:
        return None

    abs_filename = str((Path("mutants") / filename).absolute())
    lines: set[int] = set()
    if abs_filename in covered_lines:
        lines = set(covered_lines[abs_filename])

    return lines


# Gathers coverage for the given source files and
# Returns a dict of filenames to sets of lines that are covered
# Since this is run on the source files before we create mutations,
# we need to unload any modules that get loaded during the test run
def gather_coverage(runner: TestRunner, source_files: Iterable[Path]) -> dict[str, set[int]]:
    # We want to unload any python modules that get loaded
    # because we plan to mutate them and want them to be reloaded
    modules = dict(sys.modules)

    mutants_path = Path("mutants")

    # Run the tests and gather coverage
    cov = Coverage(data_file=None)
    runner.collect_main_test_coverage(cov)

    # Build mapping of filenames to covered lines
    # The CoverageData object is a wrapper around sqlite, and this
    # will make it more efficient to access the data
    covered_lines: dict[str, set[int]] = {}
    coverage_data: CoverageData = cov.get_data()

    for filename in source_files:
        abs_filename = str((mutants_path / filename).absolute())
        lines = set(coverage_data.lines(abs_filename) or [])
        covered_lines[abs_filename] = lines

    _unload_modules_not_in(modules)

    return covered_lines


# Unloads modules that are not in the 'modules' list
def _unload_modules_not_in(modules: dict[str, ModuleType]) -> None:
    for name in list(sys.modules):
        if name == "mutmut.code_coverage":
            continue
        if name not in modules:
            sys.modules.pop(name, None)
    importlib.invalidate_caches()
