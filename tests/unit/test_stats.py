"""Tests for mutmut.stats module - summary file and stats by mutation type."""

import json
from collections import defaultdict
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from mutmut.models.mutation import MutationMetadata
from mutmut.models.source_file_mutation_data import SourceFileMutationData
from mutmut.stats import Stat
from mutmut.stats import calculate_stats_by_mutation_type
from mutmut.stats import write_summary_file


class TestCalculateStatsByMutationType:
    """Tests for calculate_stats_by_mutation_type function."""

    def test_empty_data_returns_empty_dict(self):
        """Empty input returns empty dict."""
        result = calculate_stats_by_mutation_type({})
        assert result == {}

    def test_single_mutant_single_type(self, tmp_path, monkeypatch):
        """Single mutant creates stats for its type."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        mut_data = SourceFileMutationData(path="src/app.py")
        mut_data.exit_code_by_key = {"func__mutmut_1": 1}  # killed
        mut_data.mutation_metadata_by_module_name = {
            "func__mutmut_1": MutationMetadata(
                line_number=10,
                mutation_type="operator",
                description="Changed + to -",
            )
        }

        result = calculate_stats_by_mutation_type({"src/app.py": mut_data})

        assert "operator" in result
        assert result["operator"]["killed"] == 1
        assert result["operator"]["total"] == 1
        assert result["operator"]["survived"] == 0

    def test_multiple_mutation_types(self, tmp_path, monkeypatch):
        """Multiple mutation types are tracked separately."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        mut_data = SourceFileMutationData(path="src/app.py")
        mut_data.exit_code_by_key = {
            "func__mutmut_1": 1,  # killed
            "func__mutmut_2": 0,  # survived
            "func__mutmut_3": 1,  # killed
        }
        mut_data.mutation_metadata_by_module_name = {
            "func__mutmut_1": MutationMetadata(line_number=10, mutation_type="operator", description="d1"),
            "func__mutmut_2": MutationMetadata(line_number=20, mutation_type="string", description="d2"),
            "func__mutmut_3": MutationMetadata(line_number=30, mutation_type="operator", description="d3"),
        }

        result = calculate_stats_by_mutation_type({"src/app.py": mut_data})

        assert result["operator"]["total"] == 2
        assert result["operator"]["killed"] == 2
        assert result["string"]["total"] == 1
        assert result["string"]["survived"] == 1

    def test_missing_metadata_uses_unknown_type(self, tmp_path, monkeypatch):
        """Mutants without metadata are categorized as 'unknown'."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        mut_data = SourceFileMutationData(path="src/app.py")
        mut_data.exit_code_by_key = {"func__mutmut_1": 0}
        mut_data.mutation_metadata_by_module_name = {}  # No metadata

        result = calculate_stats_by_mutation_type({"src/app.py": mut_data})

        assert "unknown" in result
        assert result["unknown"]["total"] == 1
        assert result["unknown"]["survived"] == 1

    def test_multiple_files(self, tmp_path, monkeypatch):
        """Stats are aggregated across multiple files."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        mut_data1 = SourceFileMutationData(path="src/app.py")
        mut_data1.exit_code_by_key = {"func1__mutmut_1": 1}
        mut_data1.mutation_metadata_by_module_name = {
            "func1__mutmut_1": MutationMetadata(line_number=10, mutation_type="operator", description="d1"),
        }

        mut_data2 = SourceFileMutationData(path="src/utils.py")
        mut_data2.exit_code_by_key = {"func2__mutmut_1": 1}
        mut_data2.mutation_metadata_by_module_name = {
            "func2__mutmut_1": MutationMetadata(line_number=20, mutation_type="operator", description="d2"),
        }

        result = calculate_stats_by_mutation_type(
            {
                "src/app.py": mut_data1,
                "src/utils.py": mut_data2,
            }
        )

        assert result["operator"]["total"] == 2
        assert result["operator"]["killed"] == 2


class TestWriteSummaryFile:
    """Tests for write_summary_file function."""

    @pytest.fixture(autouse=True)
    def mock_name_helpers(self):
        """Mock the name-resolution helpers used inside write_summary_file."""
        with (
            patch("mutmut.stats.mangled_name_from_mutant_name", side_effect=lambda n: n.partition("__mutmut_")[0]),
            patch("mutmut.stats.orig_function_and_class_names_from_key", side_effect=lambda n: ("func", None)),
        ):
            yield

    @pytest.fixture
    def mock_state(self):
        """Mock state() to provide phase timings."""
        with patch("mutmut.stats.state") as mock:
            mock_state = MagicMock()
            mock_state.mutant_generation_time = 1.5
            mock_state.stats_time = 2.0
            mock_state.clean_tests_time = 3.0
            mock_state.forced_fail_time = 0.5
            mock_state.mutation_testing_time = 100.0
            mock_state.tests_by_mangled_function_name = defaultdict(set)
            mock.return_value = mock_state
            yield mock_state

    @pytest.fixture
    def sample_mutation_data(self, tmp_path, monkeypatch):
        """Create sample mutation data for testing."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        mut_data = SourceFileMutationData(path="src/app.py")
        mut_data.exit_code_by_key = {
            "func__mutmut_1": 0,  # survived
            "func__mutmut_2": 1,  # killed
            "func__mutmut_3": 33,  # no tests
        }
        mut_data.mutation_metadata_by_module_name = {
            "func__mutmut_1": MutationMetadata(line_number=10, mutation_type="operator", description="d1"),
            "func__mutmut_2": MutationMetadata(line_number=20, mutation_type="string", description="d2"),
            "func__mutmut_3": MutationMetadata(line_number=30, mutation_type="boolean", description="d3"),
        }
        return {"src/app.py": mut_data}

    def test_creates_summary_file(self, mock_state, sample_mutation_data):
        """write_summary_file creates mutants/summary.json."""
        stats = Stat(
            not_checked=0,
            killed=1,
            survived=1,
            total=3,
            no_tests=1,
            skipped=0,
            suspicious=0,
            timeout=0,
            check_was_interrupted_by_user=0,
            segfault=0,
            caught_by_type_check=0,
        )

        write_summary_file(
            source_file_mutation_data_by_path=sample_mutation_data,
            stats=stats,
            duration=120.0,
            count_unchanged=5,
        )

        from pathlib import Path

        summary_path = Path("mutants/summary.json")
        assert summary_path.exists()

        with open(summary_path) as f:
            data = json.load(f)

        assert "run_timestamp" in data
        assert data["total_duration_seconds"] == 120.0
        assert data["stats"]["total"] == 3
        assert data["stats"]["killed"] == 1
        assert data["stats"]["survived"] == 1
        assert data["unchanged_from_previous_run"] == 5

    def test_includes_phase_timings(self, mock_state, sample_mutation_data):
        """write_summary_file includes phase_timings from state."""
        stats = Stat(
            not_checked=0,
            killed=1,
            survived=1,
            total=3,
            no_tests=1,
            skipped=0,
            suspicious=0,
            timeout=0,
            check_was_interrupted_by_user=0,
            segfault=0,
            caught_by_type_check=0,
        )

        write_summary_file(
            source_file_mutation_data_by_path=sample_mutation_data,
            stats=stats,
            duration=120.0,
            count_unchanged=0,
        )

        with open("mutants/summary.json") as f:
            data = json.load(f)

        assert data["phase_timings"]["mutant_generation"] == 1.5
        assert data["phase_timings"]["stats_collection"] == 2.0
        assert data["phase_timings"]["clean_tests"] == 3.0
        assert data["phase_timings"]["forced_fail_test"] == 0.5
        assert data["phase_timings"]["mutation_testing"] == 100.0

    def test_includes_surviving_mutants(self, mock_state, sample_mutation_data):
        """write_summary_file includes surviving mutants with details."""
        stats = Stat(
            not_checked=0,
            killed=1,
            survived=1,
            total=3,
            no_tests=1,
            skipped=0,
            suspicious=0,
            timeout=0,
            check_was_interrupted_by_user=0,
            segfault=0,
            caught_by_type_check=0,
        )

        write_summary_file(
            source_file_mutation_data_by_path=sample_mutation_data,
            stats=stats,
            duration=120.0,
            count_unchanged=0,
        )

        with open("mutants/summary.json") as f:
            data = json.load(f)

        surviving = data["surviving_mutants"]
        assert len(surviving) == 1
        assert surviving[0]["name"] == "func__mutmut_1"
        assert surviving[0]["file"] == "src/app.py"
        assert surviving[0]["line"] == 10
        assert surviving[0]["mutation_type"] == "operator"

    def test_includes_no_tests_mutants(self, mock_state, sample_mutation_data):
        """write_summary_file includes mutants with no associated tests."""
        stats = Stat(
            not_checked=0,
            killed=1,
            survived=1,
            total=3,
            no_tests=1,
            skipped=0,
            suspicious=0,
            timeout=0,
            check_was_interrupted_by_user=0,
            segfault=0,
            caught_by_type_check=0,
        )

        write_summary_file(
            source_file_mutation_data_by_path=sample_mutation_data,
            stats=stats,
            duration=120.0,
            count_unchanged=0,
        )

        with open("mutants/summary.json") as f:
            data = json.load(f)

        no_tests = data["no_tests_mutants"]
        assert len(no_tests) == 1
        assert no_tests[0]["name"] == "func__mutmut_3"
        assert no_tests[0]["mutation_type"] == "boolean"

    def test_includes_files_with_survivors(self, mock_state, sample_mutation_data):
        """write_summary_file includes files_with_survivors count."""
        stats = Stat(
            not_checked=0,
            killed=1,
            survived=1,
            total=3,
            no_tests=1,
            skipped=0,
            suspicious=0,
            timeout=0,
            check_was_interrupted_by_user=0,
            segfault=0,
            caught_by_type_check=0,
        )

        write_summary_file(
            source_file_mutation_data_by_path=sample_mutation_data,
            stats=stats,
            duration=120.0,
            count_unchanged=0,
        )

        with open("mutants/summary.json") as f:
            data = json.load(f)

        assert data["files_with_survivors"] == {"src/app.py": 1}

    def test_calculates_mutations_per_second(self, mock_state, sample_mutation_data):
        """write_summary_file calculates mutations_per_second from mutation_testing_time."""
        mock_state.mutation_testing_time = 3.0  # 3 seconds

        stats = Stat(
            not_checked=0,
            killed=1,
            survived=1,
            total=3,
            no_tests=1,
            skipped=0,
            suspicious=0,
            timeout=0,
            check_was_interrupted_by_user=0,
            segfault=0,
            caught_by_type_check=0,
        )

        write_summary_file(
            source_file_mutation_data_by_path=sample_mutation_data,
            stats=stats,
            duration=120.0,
            count_unchanged=0,
        )

        with open("mutants/summary.json") as f:
            data = json.load(f)

        # 3 total / 3 seconds = 1.0 mutations/second
        assert data["mutations_per_second"] == 1.0
