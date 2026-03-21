"""
Statistics collection and reporting for mutmut.

This module contains the Stat dataclass and functions for collecting
and printing mutation testing statistics.
"""

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from json import JSONDecodeError

from mutmut.models.mutant_status import MutantStatus
from mutmut.models.source_file_mutation_data import SourceFileMutationData
from mutmut.models.summary import NotCheckedMutant
from mutmut.models.summary import NoTestsMutant
from mutmut.models.summary import PhaseTimings
from mutmut.models.summary import Summary
from mutmut.models.summary import SummaryStats
from mutmut.models.summary import SurvivingMutant
from mutmut.state import state
from mutmut.ui.terminal import print_status


@dataclass
class Stat:
    """Statistics for mutation testing results."""

    not_checked: int
    killed: int
    survived: int
    total: int
    no_tests: int
    skipped: int
    suspicious: int
    timeout: int
    check_was_interrupted_by_user: int
    segfault: int
    caught_by_type_check: int


def collect_stat(m: SourceFileMutationData) -> Stat:
    """Collect statistics from a SourceFileMutationData object.

    Args:
        m: The mutation data to collect stats from.

    Returns:
        A Stat object with the collected statistics.
    """
    r = {s.text.replace(" ", "_"): 0 for s in MutantStatus}
    for exit_code in m.exit_code_by_key.values():
        status = MutantStatus.from_exit_code(exit_code)
        r[status.text.replace(" ", "_")] += 1
    return Stat(
        **r,
        total=sum(r.values()),
    )


def calculate_summary_stats(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData],
) -> Stat:
    """Calculate summary statistics across all source files.

    Args:
        source_file_mutation_data_by_path: Mapping from paths to mutation data.

    Returns:
        A Stat object with the aggregated statistics.
    """
    stats = [collect_stat(x) for x in source_file_mutation_data_by_path.values()]
    return Stat(
        not_checked=sum(x.not_checked for x in stats),
        killed=sum(x.killed for x in stats),
        survived=sum(x.survived for x in stats),
        total=sum(x.total for x in stats),
        no_tests=sum(x.no_tests for x in stats),
        skipped=sum(x.skipped for x in stats),
        suspicious=sum(x.suspicious for x in stats),
        timeout=sum(x.timeout for x in stats),
        check_was_interrupted_by_user=sum(x.check_was_interrupted_by_user for x in stats),
        segfault=sum(x.segfault for x in stats),
        caught_by_type_check=sum(x.caught_by_type_check for x in stats),
    )


def print_stats(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData],
    force_output: bool = False,
) -> None:
    """Print mutation testing statistics.

    Args:
        source_file_mutation_data_by_path: Mapping from paths to mutation data.
        force_output: Whether to force output even if rate-limited.
    """
    s = calculate_summary_stats(source_file_mutation_data_by_path)
    print_status(
        f"{(s.total - s.not_checked)}/{s.total}  🎉 {s.killed} 🫥 {s.no_tests}  ⏰ {s.timeout}  🤔 {s.suspicious}  🙁 {s.survived}  🔇 {s.skipped}  🧙 {s.caught_by_type_check}",
        force_output=force_output,
    )


def load_stats() -> bool:
    did_load = False
    try:
        with open("mutants/mutmut-stats.json") as f:
            data: dict[str, object] = json.load(f)
            for k, v in data.pop("tests_by_mangled_function_name").items():  # type: ignore[attr-defined]
                state().tests_by_mangled_function_name[k] |= set(v)
            state().duration_by_test = data.pop("duration_by_test")  # type: ignore[assignment]
            state().stats_time = data.pop("stats_time")  # type: ignore[assignment]
            # Load function hashes and dependencies (backwards compatible)
            state().old_function_hashes = data.pop("function_hashes", {})  # type: ignore[assignment]
            for k, v in data.pop("function_dependencies", {}).items():  # type: ignore[attr-defined]
                state().function_dependencies[k] = set(v)
            assert not data, data
            did_load = True
    except (FileNotFoundError, JSONDecodeError):
        pass
    return did_load


def save_stats() -> None:
    with open("mutants/mutmut-stats.json", "w") as f:
        json.dump(
            {
                "tests_by_mangled_function_name": {
                    k: list(v) for k, v in state().tests_by_mangled_function_name.items()
                },
                "duration_by_test": state().duration_by_test,
                "stats_time": state().stats_time,
                "function_hashes": state().current_function_hashes,
                "function_dependencies": {k: list(v) for k, v in state().function_dependencies.items()},
            },
            f,
            indent=4,
        )


def calculate_stats_by_mutation_type(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData],
) -> dict[str, dict[str, int]]:
    """Calculate aggregate statistics broken down by mutation type and status.

    Returns a dict like:
    {
        'string': {'total': 100, 'killed': 80, 'survived': 20, 'timeout': 0, ...},
        'number': {'total': 50, 'killed': 45, 'survived': 5, 'timeout': 0, ...},
        ...
    }

    All statuses are included even if their count is 0.

    Args:
        source_file_mutation_data_by_path: Mapping from paths to mutation data.

    Returns:
        A dict mapping mutation types to their status counts.
    """
    all_statuses = [s.text for s in MutantStatus]

    def make_empty_stats() -> dict[str, int]:
        """Create a stats dict with all statuses initialized to 0."""
        stats: dict[str, int] = dict.fromkeys(all_statuses, 0)
        stats["total"] = 0
        return stats

    stats_by_type: dict[str, dict[str, int]] = defaultdict(make_empty_stats)

    for mut in source_file_mutation_data_by_path.values():
        for mutant_name, exit_code in mut.exit_code_by_key.items():
            metadata = mut.mutation_metadata_by_module_name.get(mutant_name)
            mutation_type = metadata.mutation_type if metadata else "unknown"
            status = MutantStatus.from_exit_code(exit_code)

            stats_by_type[mutation_type][status.text] += 1
            stats_by_type[mutation_type]["total"] += 1

    return {mutation_type: dict(status_counts) for mutation_type, status_counts in stats_by_type.items()}


def write_summary_file(
    source_file_mutation_data_by_path: dict[str, SourceFileMutationData],
    stats: Stat,
    duration: float,
    count_unchanged: int,
    mangled_name_from_mutant_name: Callable[[str], str],
    orig_function_and_class_names_from_key: Callable[[str], tuple[str, str | None]],
) -> None:
    """Write a summary.json file for programmatic access to mutation testing results.

    This file is designed for programmatic consumption, providing structured data about
    surviving mutants that need attention.

    Args:
        source_file_mutation_data_by_path: Dict mapping paths to SourceFileMutationData.
        stats: Stats object with aggregated statistics.
        duration: Total duration of the run in seconds.
        count_unchanged: Number of mutants skipped because they had results from previous runs.
        mangled_name_from_mutant_name: Function to convert mutant name to mangled name.
        orig_function_and_class_names_from_key: Function to extract function/class names from key.
    """
    surviving: list[SurvivingMutant] = []
    not_checked: list[NotCheckedMutant] = []
    no_tests: list[NoTestsMutant] = []
    files_with_survivors: dict[str, int] = defaultdict(int)

    for path, m in source_file_mutation_data_by_path.items():
        path_posix = path.replace("\\", "/")

        for mutant_name, exit_code in m.exit_code_by_key.items():
            func_name, _ = orig_function_and_class_names_from_key(mutant_name)
            mangled_name = mangled_name_from_mutant_name(mutant_name)
            metadata = m.mutation_metadata_by_module_name.get(mutant_name)
            associated_tests = list(state().tests_by_mangled_function_name.get(mangled_name, []))

            status = MutantStatus.from_exit_code(exit_code)
            mutation_type = metadata.mutation_type if metadata else "unknown"
            line_number = metadata.line_number if metadata else 0
            description = metadata.description if metadata else ""

            if status is MutantStatus.SURVIVED:
                surviving.append(
                    SurvivingMutant(
                        name=mutant_name,
                        file=path_posix,
                        function=func_name,
                        line=line_number,
                        mutation_type=mutation_type,
                        description=description,
                        associated_tests=associated_tests,
                    )
                )
                files_with_survivors[path_posix] += 1
            elif status is MutantStatus.NOT_CHECKED:
                not_checked.append(
                    NotCheckedMutant(
                        name=mutant_name,
                        file=path_posix,
                        function=func_name,
                        reason="run_interrupted",
                    )
                )
            elif status is MutantStatus.NO_TESTS:
                no_tests.append(
                    NoTestsMutant(
                        name=mutant_name,
                        file=path_posix,
                        function=func_name,
                        line=line_number,
                        mutation_type=mutation_type,
                        description=description,
                    )
                )

    stats_by_type_dict = calculate_stats_by_mutation_type(source_file_mutation_data_by_path)

    phase_timings = PhaseTimings(
        mutant_generation=round(state().mutant_generation_time, 3),
        stats_collection=round(state().stats_time, 3),
        clean_tests=round(state().clean_tests_time, 3),
        forced_fail_test=round(state().forced_fail_time, 3),
        mutation_testing=round(state().mutation_testing_time, 3),
    )

    summary = Summary.create(
        duration=duration,
        phase_timings=phase_timings,
        stats=SummaryStats(
            total=stats.total,
            killed=stats.killed,
            survived=stats.survived,
            no_tests=stats.no_tests,
            timeout=stats.timeout,
            suspicious=stats.suspicious,
            skipped=stats.skipped,
        ),
        stats_by_mutation_type=stats_by_type_dict,
        surviving_mutants=surviving,
        no_tests_mutants=no_tests,
        not_checked_mutants=not_checked,
        files_with_survivors=dict(files_with_survivors),
        unchanged_from_previous_run=count_unchanged,
    )

    summary.write_to_file("mutants/summary.json")
