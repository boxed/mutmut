"""Mutation-related data models."""

from dataclasses import dataclass

import libcst as cst


@dataclass
class MutationMetadata:
    """Metadata about a mutation for reporting and display purposes."""

    line_number: int
    mutation_type: str
    description: str

    def to_dict(self) -> dict[str, int | str]:
        """Serialize to a dictionary for JSON storage."""
        return {
            "line_number": self.line_number,
            "mutation_type": self.mutation_type,
            "description": self.description,
        }

    @staticmethod
    def from_dict(data: dict[str, int | str]) -> "MutationMetadata":
        """Deserialize from a dictionary."""
        return MutationMetadata(
            line_number=int(data.get("line_number", 0)),
            mutation_type=str(data.get("mutation_type", "unknown")),
            description=str(data.get("description", "")),
        )


@dataclass
class Mutation:
    """Represents a single mutation to be applied to source code.

    This class is tightly coupled to libcst and is not serializable.
    Use MutationMetadata for persistent storage of mutation information.
    """

    original_node: cst.CSTNode
    mutated_node: cst.CSTNode
    contained_by_top_level_function: cst.FunctionDef | None
    line_number: int = 0
    mutation_type: str = "unknown"
    description: str = ""

    @property
    def metadata(self) -> MutationMetadata:
        """Extract serializable metadata from this mutation."""
        return MutationMetadata(
            line_number=self.line_number,
            mutation_type=self.mutation_type,
            description=self.description,
        )
