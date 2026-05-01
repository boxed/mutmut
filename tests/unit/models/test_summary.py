"""Tests for mutmut.models.summary module."""

import json
from dataclasses import asdict

import pytest

from mutmut.models.summary import NotCheckedMutant
from mutmut.models.summary import NoTestsMutant
from mutmut.models.summary import PhaseTimings
from mutmut.models.summary import Summary
from mutmut.models.summary import SummaryStats
from mutmut.models.summary import SurvivingMutant


class TestSurvivingMutant:
    """Tests for SurvivingMutant dataclass."""

    def test_basic_creation(self):
        """SurvivingMutant can be created with all fields."""
        mutant = SurvivingMutant(
            name="test__mutmut_1",
            file="src/app.py",
            function="add",
            line=42,
            mutation_type="operator",
            description="Changed + to -",
            associated_tests=["test_add", "test_math"],
        )
        assert mutant.name == "test__mutmut_1"
        assert mutant.file == "src/app.py"
        assert mutant.function == "add"
        assert mutant.line == 42
        assert mutant.mutation_type == "operator"
        assert mutant.description == "Changed + to -"
        assert mutant.associated_tests == ["test_add", "test_math"]

    def test_default_associated_tests(self):
        """associated_tests defaults to empty list."""
        mutant = SurvivingMutant(
            name="test__mutmut_1",
            file="src/app.py",
            function="add",
            line=42,
            mutation_type="operator",
            description="Changed + to -",
        )
        assert mutant.associated_tests == []

    def test_asdict_serialization(self):
        """SurvivingMutant can be serialized with asdict."""
        mutant = SurvivingMutant(
            name="test__mutmut_1",
            file="src/app.py",
            function="add",
            line=42,
            mutation_type="operator",
            description="Changed + to -",
            associated_tests=["test_add"],
        )
        d = asdict(mutant)
        assert d == {
            "name": "test__mutmut_1",
            "file": "src/app.py",
            "function": "add",
            "line": 42,
            "mutation_type": "operator",
            "description": "Changed + to -",
            "associated_tests": ["test_add"],
        }


class TestNotCheckedMutant:
    """Tests for NotCheckedMutant dataclass."""

    def test_basic_creation(self):
        """NotCheckedMutant can be created with all fields."""
        mutant = NotCheckedMutant(
            name="test__mutmut_2",
            file="src/app.py",
            function="subtract",
            reason="timeout",
        )
        assert mutant.name == "test__mutmut_2"
        assert mutant.file == "src/app.py"
        assert mutant.function == "subtract"
        assert mutant.reason == "timeout"

    def test_default_reason(self):
        """reason defaults to 'run_interrupted'."""
        mutant = NotCheckedMutant(
            name="test__mutmut_2",
            file="src/app.py",
            function="subtract",
        )
        assert mutant.reason == "run_interrupted"


class TestNoTestsMutant:
    """Tests for NoTestsMutant dataclass."""

    def test_basic_creation(self):
        """NoTestsMutant can be created with all fields."""
        mutant = NoTestsMutant(
            name="test__mutmut_3",
            file="src/utils.py",
            function="helper",
            line=100,
            mutation_type="string",
            description="Changed 'hello' to 'world'",
        )
        assert mutant.name == "test__mutmut_3"
        assert mutant.file == "src/utils.py"
        assert mutant.function == "helper"
        assert mutant.line == 100
        assert mutant.mutation_type == "string"
        assert mutant.description == "Changed 'hello' to 'world'"


class TestPhaseTimings:
    """Tests for PhaseTimings dataclass."""

    def test_all_none_by_default(self):
        """All phase timings default to None."""
        timings = PhaseTimings()
        assert timings.mutant_generation is None
        assert timings.stats_collection is None
        assert timings.clean_tests is None
        assert timings.forced_fail_test is None
        assert timings.mutation_testing is None

    def test_partial_timings(self):
        """Can set some timings while leaving others None."""
        timings = PhaseTimings(
            mutant_generation=1.5,
            mutation_testing=100.0,
        )
        assert timings.mutant_generation == 1.5
        assert timings.stats_collection is None
        assert timings.mutation_testing == 100.0

    def test_all_timings(self):
        """Can set all timings."""
        timings = PhaseTimings(
            mutant_generation=1.5,
            stats_collection=2.0,
            clean_tests=3.0,
            forced_fail_test=0.5,
            mutation_testing=100.0,
        )
        assert timings.mutant_generation == 1.5
        assert timings.stats_collection == 2.0
        assert timings.clean_tests == 3.0
        assert timings.forced_fail_test == 0.5
        assert timings.mutation_testing == 100.0

    def test_asdict_serialization(self):
        """PhaseTimings can be serialized with asdict."""
        timings = PhaseTimings(
            mutant_generation=1.5,
            stats_collection=None,
            mutation_testing=100.0,
        )
        d = asdict(timings)
        assert d == {
            "mutant_generation": 1.5,
            "stats_collection": None,
            "clean_tests": None,
            "forced_fail_test": None,
            "mutation_testing": 100.0,
        }


class TestSummaryStats:
    """Tests for SummaryStats dataclass."""

    def test_basic_creation(self):
        """SummaryStats can be created with all fields."""
        stats = SummaryStats(
            total=100,
            killed=80,
            survived=10,
            no_tests=5,
            timeout=2,
            suspicious=1,
            skipped=2,
        )
        assert stats.total == 100
        assert stats.killed == 80
        assert stats.survived == 10
        assert stats.no_tests == 5
        assert stats.timeout == 2
        assert stats.suspicious == 1
        assert stats.skipped == 2

    def test_asdict_serialization(self):
        """SummaryStats can be serialized with asdict."""
        stats = SummaryStats(
            total=100,
            killed=80,
            survived=10,
            no_tests=5,
            timeout=2,
            suspicious=1,
            skipped=2,
        )
        d = asdict(stats)
        assert d == {
            "total": 100,
            "killed": 80,
            "survived": 10,
            "no_tests": 5,
            "timeout": 2,
            "suspicious": 1,
            "skipped": 2,
        }


class TestSummary:
    """Tests for Summary dataclass."""

    @pytest.fixture
    def sample_stats(self):
        """Create sample SummaryStats."""
        return SummaryStats(
            total=100,
            killed=80,
            survived=10,
            no_tests=5,
            timeout=2,
            suspicious=1,
            skipped=2,
        )

    @pytest.fixture
    def sample_phase_timings(self):
        """Create sample PhaseTimings."""
        return PhaseTimings(
            mutant_generation=1.5,
            stats_collection=2.0,
            clean_tests=3.0,
            forced_fail_test=0.5,
            mutation_testing=100.0,
        )

    @pytest.fixture
    def sample_surviving_mutant(self):
        """Create sample SurvivingMutant."""
        return SurvivingMutant(
            name="test__mutmut_1",
            file="src/app.py",
            function="add",
            line=42,
            mutation_type="operator",
            description="Changed + to -",
            associated_tests=["test_add"],
        )

    def test_create_sets_timestamp(self, sample_stats, sample_phase_timings):
        """Summary.create() sets run_timestamp."""
        summary = Summary.create(
            duration=120.0,
            phase_timings=sample_phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )
        # Should be ISO format timestamp
        assert "T" in summary.run_timestamp

    def test_create_rounds_duration(self, sample_stats, sample_phase_timings):
        """Summary.create() rounds total_duration_seconds to 2 decimal places."""
        summary = Summary.create(
            duration=123.456789,
            phase_timings=sample_phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )
        assert summary.total_duration_seconds == 123.46

    def test_create_calculates_mutations_per_second(self, sample_stats, sample_phase_timings):
        """Summary.create() calculates mutations_per_second from stats.total / mutation_testing_time."""
        summary = Summary.create(
            duration=120.0,
            phase_timings=sample_phase_timings,  # mutation_testing=100.0
            stats=sample_stats,  # total=100
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )
        # 100 mutants / 100 seconds = 1.0 mutations/second
        assert summary.mutations_per_second == 1.0

    def test_create_handles_zero_mutation_testing_time(self, sample_stats):
        """Summary.create() returns 0 mutations_per_second when mutation_testing is 0."""
        phase_timings = PhaseTimings(mutation_testing=0)
        summary = Summary.create(
            duration=120.0,
            phase_timings=phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )
        assert summary.mutations_per_second == 0

    def test_create_handles_none_mutation_testing_time(self, sample_stats):
        """Summary.create() returns 0 mutations_per_second when mutation_testing is None."""
        phase_timings = PhaseTimings(mutation_testing=None)
        summary = Summary.create(
            duration=120.0,
            phase_timings=phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )
        assert summary.mutations_per_second == 0

    def test_to_dict_serialization(self, sample_stats, sample_phase_timings, sample_surviving_mutant):
        """Summary.to_dict() returns a JSON-serializable dict."""
        surviving = [sample_surviving_mutant]
        not_checked = [NotCheckedMutant(name="m2", file="f.py", function="f")]
        no_tests = [NoTestsMutant(name="m3", file="f.py", function="g", line=10, mutation_type="op", description="d")]

        summary = Summary.create(
            duration=120.0,
            phase_timings=sample_phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={"operator": {"killed": 50, "survived": 5}},
            surviving_mutants=surviving,
            no_tests_mutants=no_tests,
            not_checked_mutants=not_checked,
            files_with_survivors={"src/app.py": 1},
            unchanged_from_previous_run=5,
        )

        d = summary.to_dict()

        # Verify structure
        assert "run_timestamp" in d
        assert d["total_duration_seconds"] == 120.0
        assert d["mutations_per_second"] == 1.0
        assert d["phase_timings"]["mutant_generation"] == 1.5
        assert d["phase_timings"]["mutation_testing"] == 100.0
        assert d["stats"]["total"] == 100
        assert d["stats"]["killed"] == 80
        assert d["stats_by_mutation_type"] == {"operator": {"killed": 50, "survived": 5}}
        assert len(d["surviving_mutants"]) == 1
        assert d["surviving_mutants"][0]["name"] == "test__mutmut_1"
        assert len(d["no_tests_mutants"]) == 1
        assert len(d["not_checked_mutants"]) == 1
        assert d["files_with_survivors"] == {"src/app.py": 1}
        assert d["unchanged_from_previous_run"] == 5

        # Verify JSON serializable
        json.dumps(d)  # Should not raise

    def test_write_to_file(self, tmp_path, sample_stats, sample_phase_timings):
        """Summary.write_to_file() writes valid JSON."""
        summary = Summary.create(
            duration=120.0,
            phase_timings=sample_phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )

        output_path = tmp_path / "summary.json"
        summary.write_to_file(output_path)

        # Verify file was written
        assert output_path.exists()

        # Verify valid JSON
        with open(output_path) as f:
            data = json.load(f)

        assert data["total_duration_seconds"] == 120.0
        assert data["stats"]["total"] == 100

    def test_write_to_file_with_string_path(self, tmp_path, sample_stats, sample_phase_timings, monkeypatch):
        """Summary.write_to_file() accepts string path."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        summary = Summary.create(
            duration=60.0,
            phase_timings=sample_phase_timings,
            stats=sample_stats,
            stats_by_mutation_type={},
            surviving_mutants=[],
            no_tests_mutants=[],
            not_checked_mutants=[],
            files_with_survivors={},
            unchanged_from_previous_run=0,
        )

        summary.write_to_file("mutants/summary.json")

        assert (tmp_path / "mutants" / "summary.json").exists()
