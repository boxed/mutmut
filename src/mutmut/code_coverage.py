from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from multiprocessing import get_context
from pathlib import Path
from typing import TYPE_CHECKING

import coverage
from coverage import CoverageData
from coverage.exceptions import CoverageException

from mutmut.configuration import get_mutants_dir

if TYPE_CHECKING:
    from mutmut.runners.harness import TestRunner


@dataclass
class CoverageInfo:
    """What coverage.py knows about the source files, keyed by resolved path in the mutants directory.

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

    abs_filename = str((get_mutants_dir() / filename).resolve())
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

    abs_filename = str((get_mutants_dir() / filename).resolve())
    return set(excluded_lines.get(abs_filename, ()))


def gather_coverage(runner: TestRunner, source_files: Iterable[Path]) -> CoverageInfo:
    """Gathers coverage for the given source files in a throwaway child process.

    Returns the covered and excluded lines of each of them. Forking keeps the test
    suite's imports out of the main process, which imports the same modules again
    later and cannot always survive it (#528).
    """
    if sys.platform == "win32":
        with get_context("spawn").Pool(1) as pool:
            spawned_result: CoverageInfo = pool.apply(_gather_coverage_in_spawned_process, (runner, source_files))
        return spawned_result

    from mutmut.workers.isolation import run_in_fork_with_result

    result: CoverageInfo = run_in_fork_with_result(_gather_coverage_in_this_process, runner, source_files)
    return result


def _gather_coverage_in_spawned_process(runner: TestRunner, source_files: Iterable[Path]) -> CoverageInfo:
    """Sets up what a forked child would have inherited, then measures."""
    from mutmut.configuration import config
    from mutmut.utils.file_utils import setup_source_paths

    setup_source_paths()
    if not config().debug:
        sys.stdout = sys.stderr = open(os.devnull, "w", encoding="utf-8")
    return _gather_coverage_in_this_process(runner, source_files)


def _gather_coverage_in_this_process(runner: TestRunner, source_files: Iterable[Path]) -> CoverageInfo:
    """The actual measurement. Pollutes the calling process; see gather_coverage."""
    # Run the tests and gather coverage. When mutants_dir lives outside the
    # project root, coverage.py's default cwd-based filter would ignore it
    # unless we explicitly point `source` at the mutants directory.
    resolved_mutants = get_mutants_dir().resolve()
    source = (
        [str(resolved_mutants)]
        if resolved_mutants.is_dir() and not resolved_mutants.is_relative_to(Path.cwd().resolve())
        else None
    )
    cov = coverage.Coverage(data_file=None, source=source)
    runner.collect_main_test_coverage(cov)

    # Build mapping of filenames to covered lines
    # The CoverageData object is a wrapper around sqlite, and this
    # will make it more efficient to access the data
    info = CoverageInfo()
    coverage_data: CoverageData = cov.get_data()

    for filename in source_files:
        abs_filename = str((resolved_mutants / filename).resolve())
        info.covered_lines[abs_filename] = set(coverage_data.lines(abs_filename) or [])
        info.excluded_lines[abs_filename] = _excluded_lines(cov, abs_filename)

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
