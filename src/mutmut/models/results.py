"""Result-related data models for worker communication and persistence."""

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any


@dataclass
class FileMutationResult:
    """Result from creating mutants for a single file.

    Used to transfer warnings, errors, and metadata from child processes
    to the parent during parallel mutant generation.
    """

    warnings: list[Warning] = field(default_factory=list)
    error: Exception | None = None
    unmodified: bool = False
    ignored: bool = False
    changed_functions: set[str] | None = None
    current_hashes: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage.

        Note: warnings and error are converted to string representations
        since Warning and Exception objects are not directly JSON serializable.
        """
        return {
            "warnings": [str(w) for w in self.warnings],
            "error": str(self.error) if self.error else None,
            "unmodified": self.unmodified,
            "ignored": self.ignored,
            "changed_functions": list(self.changed_functions) if self.changed_functions else [],
            "current_hashes": self.current_hashes or {},
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "FileMutationResult":
        """Deserialize from a dictionary.

        Note: warnings are restored as UserWarning and error as generic Exception
        since the original types cannot be reconstructed from strings.
        """
        error_str = data.get("error")
        changed = data.get("changed_functions", [])
        hashes = data.get("current_hashes", {})
        return FileMutationResult(
            warnings=[UserWarning(w) for w in data.get("warnings", [])],
            error=Exception(error_str) if error_str else None,
            unmodified=data.get("unmodified", False),
            ignored=data.get("ignored", False),
            changed_functions=set(changed) if changed is not None else None,
            current_hashes=hashes if hashes is not None else None,
        )


@dataclass
class MutantGenerationStats:
    """Stats from mutant generation phase (mutated, unmodified, ignored counts)."""

    mutated: int = 0
    unmodified: int = 0
    ignored: int = 0


@dataclass(slots=True)
class MutantTestResult:
    """Result of testing a single mutant.

    Used for streaming results from worker processes back to the main process.
    """

    mutant_name: str
    exit_code: int
    duration: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage or IPC."""
        return {
            "mutant_name": self.mutant_name,
            "exit_code": self.exit_code,
            "duration": self.duration,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MutantTestResult":
        """Deserialize from a dictionary."""
        return MutantTestResult(
            mutant_name=str(data.get("mutant_name", "")),
            exit_code=int(data.get("exit_code", -1)),
            duration=float(data.get("duration", 0.0)),
        )


@dataclass(slots=True)
class WorkerResult:
    """Result from a worker process after testing mutants for a file.

    Contains all test results for mutants in a single source file,
    along with collected timing and test mapping data.
    """

    source_path: Path
    mutant_results: list[MutantTestResult]
    duration_by_test: dict[str, float] = field(default_factory=dict)
    tests_by_mangled_function_name: dict[str, set[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage or IPC.

        Note: sets in tests_by_mangled_function_name are converted to lists.
        """
        return {
            "source_path": str(self.source_path),
            "mutant_results": [r.to_dict() for r in self.mutant_results],
            "duration_by_test": self.duration_by_test,
            "tests_by_mangled_function_name": {k: list(v) for k, v in self.tests_by_mangled_function_name.items()},
            "errors": self.errors,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "WorkerResult":
        """Deserialize from a dictionary."""
        return WorkerResult(
            source_path=Path(data.get("source_path", "")),
            mutant_results=[MutantTestResult.from_dict(r) for r in data.get("mutant_results", [])],
            duration_by_test=data.get("duration_by_test", {}),
            tests_by_mangled_function_name={
                k: set(v) for k, v in data.get("tests_by_mangled_function_name", {}).items()
            },
            errors=data.get("errors", []),
        )
