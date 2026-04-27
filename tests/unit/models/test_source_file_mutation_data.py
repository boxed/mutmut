"""Tests for mutmut.models.source_file_mutation_data module."""

from mutmut.models.mutation import MutationMetadata
from mutmut.models.source_file_mutation_data import SourceFileMutationData


class TestSourceFileMutationData:
    """Tests for SourceFileMutationData serialization."""

    def test_to_dict_contains_all_fields(self):
        """Verify to_dict includes all fields."""
        data = SourceFileMutationData(path="src/module.py")
        data.exit_code_by_key = {"m1": 1, "m2": 0}
        data.durations_by_key = {"m1": 1.0, "m2": 2.0}
        data.estimated_time_of_tests_by_mutant = {"m1": 1.5}
        data.hash_by_function_name = {"func1": "abc123"}
        data.mutation_metadata_by_module_name = {
            "m1": MutationMetadata(line_number=10, mutation_type="operator", description="+ to -")
        }

        d = data.to_dict()
        assert d["path"] == "src/module.py"
        assert d["exit_code_by_key"] == {"m1": 1, "m2": 0}
        assert d["durations_by_key"] == {"m1": 1.0, "m2": 2.0}
        assert d["hash_by_function_name"] == {"func1": "abc123"}
        assert "m1" in d["mutation_metadata_by_module_name"]

    def test_from_dict_creates_equivalent_object(self):
        """Verify from_dict creates an equivalent object."""
        data_dict = {
            "path": "src/lib.py",
            "exit_code_by_key": {"m1": 1},
            "durations_by_key": {"m1": 0.5},
            "estimated_time_of_tests_by_mutant": {},
            "hash_by_function_name": {"func": "hash1"},
            "mutation_metadata_by_module_name": {
                "m1": {"line_number": 5, "mutation_type": "boolean", "description": "True to False"}
            },
        }
        result = SourceFileMutationData.from_dict(data_dict)
        assert result.path == "src/lib.py"
        assert result.exit_code_by_key == {"m1": 1}
        assert result.hash_by_function_name == {"func": "hash1"}
        assert result.mutation_metadata_by_module_name["m1"].line_number == 5

    def test_round_trip(self):
        """Test serialization round-trip."""
        original = SourceFileMutationData(path="test/path.py")
        original.exit_code_by_key = {"mut1": 1}
        original.durations_by_key = {"mut1": 0.25}
        original.estimated_time_of_tests_by_mutant = {"mut1": 0.3}
        original.hash_by_function_name = {"f1": "hash_abc"}
        original.mutation_metadata_by_module_name = {
            "mut1": MutationMetadata(line_number=42, mutation_type="statement", description="Removed x = 1")
        }

        serialized = original.to_dict()
        restored = SourceFileMutationData.from_dict(serialized)

        assert restored.path == original.path
        assert restored.exit_code_by_key == original.exit_code_by_key
        assert restored.durations_by_key == original.durations_by_key
        assert restored.estimated_time_of_tests_by_mutant == original.estimated_time_of_tests_by_mutant
        assert restored.hash_by_function_name == original.hash_by_function_name
        assert restored.mutation_metadata_by_module_name["mut1"] == original.mutation_metadata_by_module_name["mut1"]

    def test_runtime_state_not_serialized(self):
        """Verify runtime state (key_by_pid, start_time_by_pid) is not serialized."""
        original = SourceFileMutationData(path="test.py")
        # Runtime state would normally be set during test execution
        # But it should not appear in to_dict output
        d = original.to_dict()
        assert "key_by_pid" not in d
        assert "start_time_by_pid" not in d
