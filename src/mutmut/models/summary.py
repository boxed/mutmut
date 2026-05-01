"""Summary data models for mutation testing results.

This module contains dataclasses for representing mutation testing summary data,
designed for JSON serialization and programmatic consumption of results.
"""

import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from pathlib import Path


@dataclass
class SurvivingMutant:
    """A mutant that survived (tests passed despite the mutation)."""

    name: str
    file: str
    function: str
    line: int
    mutation_type: str
    description: str
    associated_tests: list[str] = field(default_factory=list)


@dataclass
class NotCheckedMutant:
    """A mutant that was not checked (run was interrupted)."""

    name: str
    file: str
    function: str
    reason: str = "run_interrupted"


@dataclass
class NoTestsMutant:
    """A mutant with no associated tests."""

    name: str
    file: str
    function: str
    line: int
    mutation_type: str
    description: str


@dataclass
class PhaseTimings:
    """Timing information for each phase of the mutation testing run."""

    mutant_generation: float | None = None
    stats_collection: float | None = None
    clean_tests: float | None = None
    forced_fail_test: float | None = None
    mutation_testing: float | None = None


@dataclass
class SummaryStats:
    """Aggregated statistics for a mutation testing run."""

    total: int
    killed: int
    survived: int
    no_tests: int
    timeout: int
    suspicious: int
    skipped: int


@dataclass
class Summary:
    """Complete summary of a mutation testing run.

    This is the top-level model for the summary.json file, designed for
    programmatic consumption of mutation testing results.
    """

    run_timestamp: str
    total_duration_seconds: float
    mutations_per_second: float
    phase_timings: PhaseTimings
    stats: SummaryStats
    stats_by_mutation_type: dict[str, dict[str, int]]
    surviving_mutants: list[SurvivingMutant]
    no_tests_mutants: list[NoTestsMutant]
    not_checked_mutants: list[NotCheckedMutant]
    files_with_survivors: dict[str, int]
    unchanged_from_previous_run: int

    @classmethod
    def create(
        cls,
        *,
        duration: float,
        phase_timings: PhaseTimings,
        stats: SummaryStats,
        stats_by_mutation_type: dict[str, dict[str, int]],
        surviving_mutants: list[SurvivingMutant],
        no_tests_mutants: list[NoTestsMutant],
        not_checked_mutants: list[NotCheckedMutant],
        files_with_survivors: dict[str, int],
        unchanged_from_previous_run: int,
    ) -> "Summary":
        """Create a Summary with computed fields.

        Args:
            duration: Total duration of the run in seconds.
            phase_timings: Timing information for each phase.
            stats: Aggregated statistics.
            stats_by_mutation_type: Stats broken down by mutation type.
            surviving_mutants: List of surviving mutants.
            no_tests_mutants: List of mutants with no tests.
            not_checked_mutants: List of unchecked mutants.
            files_with_survivors: Map of file paths to survivor counts.
            unchanged_from_previous_run: Count of skipped mutants.

        Returns:
            A fully populated Summary instance.
        """
        mutation_testing_time = phase_timings.mutation_testing
        return cls(
            run_timestamp=datetime.now().isoformat(),
            total_duration_seconds=round(duration, 2),
            mutations_per_second=(
                round(stats.total / mutation_testing_time, 2)
                if mutation_testing_time and mutation_testing_time > 0
                else 0
            ),
            phase_timings=phase_timings,
            stats=stats,
            stats_by_mutation_type=stats_by_mutation_type,
            surviving_mutants=surviving_mutants,
            no_tests_mutants=no_tests_mutants,
            not_checked_mutants=not_checked_mutants,
            files_with_survivors=files_with_survivors,
            unchanged_from_previous_run=unchanged_from_previous_run,
        )

    def to_dict(self) -> dict[str, object]:
        """Convert to a dictionary suitable for JSON serialization."""
        return {
            "run_timestamp": self.run_timestamp,
            "total_duration_seconds": self.total_duration_seconds,
            "mutations_per_second": self.mutations_per_second,
            "phase_timings": asdict(self.phase_timings),
            "stats": asdict(self.stats),
            "stats_by_mutation_type": self.stats_by_mutation_type,
            "surviving_mutants": [asdict(m) for m in self.surviving_mutants],
            "no_tests_mutants": [asdict(m) for m in self.no_tests_mutants],
            "not_checked_mutants": [asdict(m) for m in self.not_checked_mutants],
            "files_with_survivors": self.files_with_survivors,
            "unchanged_from_previous_run": self.unchanged_from_previous_run,
        }

    def write_to_file(self, path: str | Path = "mutants/summary.json") -> None:
        """Write the summary to a JSON file.

        Args:
            path: Path to write the summary file to.
        """
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
