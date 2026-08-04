from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import coverage
from coverage import CoverageData
from coverage.exceptions import CoverageException

if TYPE_CHECKING:
    from mutmut.__main__ import TestRunner


@dataclass
class CoverageInfo:
    """What coverage.py knows about the source files, keyed by absolute path in `mutants/`.

    `covered_lines` are the lines that actually executed. `excluded_lines` are the lines
    coverage.py was told to ignore (`# pragma: no cover`, `exclude_lines`, `exclude_also`).
    The two are kept apart rather than subtracted, because an excluded line that runs is
    also a covered line, and the two are used differently: coverage.py reports only the
    *first* line of each excluded statement, so those have to be expanded to full
    statements before they mean anything to the mutation visitor.
    """

    covered_lines: dict[str, set[int]] = field(default_factory=dict)
    excluded_lines: dict[str, set[int]] = field(default_factory=dict)


# Returns a set of lines that are covered in this file gvein the covered_lines dict
#  returned by gather_coverage
# None means it's not enabled, set() means no lines are covered
def get_covered_lines_for_file(filename: str, covered_lines: dict[str, set[int]] | None) -> set[int] | None:
    if covered_lines is None or filename is None:
        return None

    abs_filename = str((Path("mutants") / filename).absolute())
    lines: set[int] = set()
    if abs_filename in covered_lines:
        lines = set(covered_lines[abs_filename])

    return lines


# Returns the lines coverage.py excludes from measurement in this file, given the
# excluded_lines dict returned by gather_coverage. An empty set means nothing is excluded,
# which is also what we get when the feature is disabled.
def get_excluded_lines_for_file(filename: str, excluded_lines: dict[str, set[int]] | None) -> set[int]:
    if excluded_lines is None or filename is None:
        return set()

    abs_filename = str((Path("mutants") / filename).absolute())
    return set(excluded_lines.get(abs_filename, ()))


# Gathers coverage for the given source files and
# Returns the covered and excluded lines of each of them
# Since this is run on the source files before we create mutations,
# we need to unload any modules that get loaded during the test run
def gather_coverage(runner: TestRunner, source_files: Iterable[Path]) -> CoverageInfo:
    # We want to unload any python modules that get loaded
    # because we plan to mutate them and want them to be reloaded
    modules = dict(sys.modules)

    mutants_path = Path("mutants")

    # Run the tests and gather coverage
    cov = coverage.Coverage(data_file=None)
    runner.collect_main_test_coverage(cov)

    # Build mapping of filenames to covered lines
    # The CoverageData object is a wrapper around sqlite, and this
    # will make it more efficient to access the data
    info = CoverageInfo()
    coverage_data: CoverageData = cov.get_data()

    for filename in source_files:
        abs_filename = str((mutants_path / filename).absolute())
        info.covered_lines[abs_filename] = set(coverage_data.lines(abs_filename) or [])
        info.excluded_lines[abs_filename] = _excluded_lines(cov, abs_filename)

    _unload_modules_not_in(modules)

    return info


# Asks coverage.py which lines of this file are excluded from measurement.
# This is analysis of the source, not of the collected data, so it is also
# correct for files the test run never imported.
def _excluded_lines(cov: coverage.Coverage, abs_filename: str) -> set[int]:
    try:
        _, _, excluded, _, _ = cov.analysis2(abs_filename)
    except CoverageException:
        # Unparseable or missing source: nothing we can say about it
        return set()

    return set(excluded)


# Unloads modules that are not in the 'modules' list
def _unload_modules_not_in(modules: dict[str, ModuleType]) -> None:
    for name in list(sys.modules):
        if name == "mutmut.code_coverage":
            continue
        if name not in modules:
            sys.modules.pop(name, None)
    importlib.invalidate_caches()
