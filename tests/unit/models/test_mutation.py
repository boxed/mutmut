"""Tests for mutmut.models.mutation module."""

from mutmut.models.mutation import MutationMetadata


class TestMutationMetadata:
    """Tests for MutationMetadata serialization."""

    def test_to_dict_contains_all_fields(self):
        """Verify to_dict includes all fields."""
        metadata = MutationMetadata(
            line_number=42,
            mutation_type="operator",
            description="Changed + to -",
        )
        d = metadata.to_dict()
        assert d == {
            "line_number": 42,
            "mutation_type": "operator",
            "description": "Changed + to -",
        }

    def test_from_dict_creates_equivalent_object(self):
        """Verify from_dict creates an equivalent object."""
        data = {
            "line_number": 42,
            "mutation_type": "operator",
            "description": "Changed + to -",
        }
        metadata = MutationMetadata.from_dict(data)
        assert metadata.line_number == 42
        assert metadata.mutation_type == "operator"
        assert metadata.description == "Changed + to -"

    def test_round_trip(self):
        """Test serialization round-trip."""
        original = MutationMetadata(
            line_number=100,
            mutation_type="boolean",
            description="Changed True to False",
        )
        serialized = original.to_dict()
        restored = MutationMetadata.from_dict(serialized)
        assert restored == original
