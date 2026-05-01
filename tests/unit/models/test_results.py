"""Tests for mutmut.models.results module."""

from pathlib import Path

from mutmut.models.results import FileMutationResult
from mutmut.models.results import MutantTestResult
from mutmut.models.results import WorkerResult


class TestMutantTestResult:
    """Tests for MutantTestResult serialization."""

    def test_to_dict_contains_all_fields(self):
        """Verify to_dict includes all fields."""
        result = MutantTestResult(
            mutant_name="foo__mutmut_1",
            exit_code=1,
            duration=1.234,
        )
        d = result.to_dict()
        assert d == {
            "mutant_name": "foo__mutmut_1",
            "exit_code": 1,
            "duration": 1.234,
        }

    def test_from_dict_creates_equivalent_object(self):
        """Verify from_dict creates an equivalent object."""
        data = {
            "mutant_name": "bar__mutmut_2",
            "exit_code": 0,
            "duration": 5.678,
        }
        result = MutantTestResult.from_dict(data)
        assert result.mutant_name == "bar__mutmut_2"
        assert result.exit_code == 0
        assert result.duration == 5.678

    def test_round_trip(self):
        """Test serialization round-trip."""
        original = MutantTestResult(
            mutant_name="test_func__mutmut_3",
            exit_code=1,
            duration=0.5,
        )
        serialized = original.to_dict()
        restored = MutantTestResult.from_dict(serialized)
        assert restored == original


class TestWorkerResult:
    """Tests for WorkerResult serialization."""

    def test_to_dict_contains_all_fields(self):
        """Verify to_dict includes all fields."""
        result = WorkerResult(
            source_path=Path("src/app/module.py"),
            mutant_results=[
                MutantTestResult(mutant_name="m1", exit_code=1, duration=1.0),
                MutantTestResult(mutant_name="m2", exit_code=0, duration=2.0),
            ],
            duration_by_test={"test_a": 0.5, "test_b": 1.5},
            tests_by_mangled_function_name={"func1": {"test_a", "test_b"}, "func2": {"test_a"}},
            errors=["Some error occurred"],
        )
        d = result.to_dict()
        assert d["source_path"] == "src/app/module.py"
        assert len(d["mutant_results"]) == 2
        assert d["duration_by_test"] == {"test_a": 0.5, "test_b": 1.5}
        # Sets are converted to lists
        assert set(d["tests_by_mangled_function_name"]["func1"]) == {"test_a", "test_b"}
        assert d["errors"] == ["Some error occurred"]

    def test_from_dict_creates_equivalent_object(self):
        """Verify from_dict creates an equivalent object."""
        data = {
            "source_path": "src/lib.py",
            "mutant_results": [
                {"mutant_name": "m1", "exit_code": 1, "duration": 1.0},
            ],
            "duration_by_test": {"test_x": 0.1},
            "tests_by_mangled_function_name": {"bar": ["test_x"]},
            "errors": None,
        }
        result = WorkerResult.from_dict(data)
        assert result.source_path == Path("src/lib.py")
        assert len(result.mutant_results) == 1
        assert result.mutant_results[0].mutant_name == "m1"
        assert result.duration_by_test == {"test_x": 0.1}
        assert result.tests_by_mangled_function_name == {"bar": {"test_x"}}
        assert result.errors is None

    def test_round_trip(self):
        """Test serialization round-trip."""
        original = WorkerResult(
            source_path=Path("path/to/file.py"),
            mutant_results=[
                MutantTestResult(mutant_name="func__mutmut_1", exit_code=1, duration=2.5),
            ],
            duration_by_test={"test_func": 2.5},
            tests_by_mangled_function_name={"func": {"test_func"}},
            errors=None,
        )
        serialized = original.to_dict()
        restored = WorkerResult.from_dict(serialized)
        assert restored == original

    def test_round_trip_with_empty_collections(self):
        """Test round-trip with empty collections."""
        original = WorkerResult(
            source_path=Path("empty.py"),
            mutant_results=[],
            duration_by_test={},
            tests_by_mangled_function_name={},
            errors=None,
        )
        serialized = original.to_dict()
        restored = WorkerResult.from_dict(serialized)
        assert restored == original


class TestFileMutationResult:
    """Tests for FileMutationResult serialization."""

    def test_to_dict_contains_all_fields(self):
        """Verify to_dict includes all fields."""
        result = FileMutationResult(
            warnings=[UserWarning("Test warning")],
            error=ValueError("Test error"),
            changed_functions={"func1", "func2"},
            current_hashes={"func1": "abc123"},
        )
        d = result.to_dict()
        assert len(d["warnings"]) == 1
        assert d["error"] == "Test error"
        assert set(d["changed_functions"]) == {"func1", "func2"}
        assert d["current_hashes"] == {"func1": "abc123"}

    def test_from_dict_creates_equivalent_object(self):
        """Verify from_dict creates an equivalent object."""
        data = {
            "warnings": ["Warning message"],
            "error": "Error message",
            "changed_functions": ["func_a"],
            "current_hashes": {"func_a": "xyz789"},
        }
        result = FileMutationResult.from_dict(data)
        assert len(result.warnings) == 1
        assert isinstance(result.warnings[0], UserWarning)
        assert isinstance(result.error, Exception)
        assert result.changed_functions == {"func_a"}
        assert result.current_hashes == {"func_a": "xyz789"}

    def test_round_trip_with_none_values(self):
        """Test round-trip with None values."""
        original = FileMutationResult(
            warnings=[],
            error=None,
        )
        serialized = original.to_dict()
        restored = FileMutationResult.from_dict(serialized)
        assert restored.warnings == []
        assert restored.error is None
        assert restored.changed_functions == set()
        assert restored.current_hashes == {}
