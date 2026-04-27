"""Source file mutation data model for tracking mutation testing results."""

import json
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

from mutmut.models.mutation import MutationMetadata


class SourceFileMutationData:
    """Tracks mutation testing data for a single source file.

    Manages:
    - Test exit codes and durations for each mutant
    - Estimated test times for scheduling
    - Function hashes for invalidation detection
    - Mutation metadata for reporting
    """

    def __init__(self, *, path: Path | str) -> None:
        self.estimated_time_of_tests_by_mutant: dict[str, float] = {}
        self.path = path
        self.meta_path = Path("mutants") / (str(path) + ".meta")
        self.key_by_pid: dict[int, str] = {}
        self.exit_code_by_key: dict[str, int | None] = {}
        self.durations_by_key: dict[str, float] = {}
        self.start_time_by_pid: dict[int, datetime] = {}
        self.type_check_error_by_key: dict[str, str | None] = {}
        self.hash_by_function_name: dict[str, str] = {}
        self.mutation_metadata_by_module_name: dict[str, MutationMetadata] = {}

    def load(self) -> None:
        """Load mutation data from the meta file."""
        try:
            with open(self.meta_path) as f:
                meta: dict[str, Any] = json.load(f)
        except FileNotFoundError:
            return

        self.exit_code_by_key = meta.pop("exit_code_by_key")
        self.type_check_error_by_key = meta.pop("type_check_error_by_key", {})
        self.durations_by_key = meta.pop("durations_by_key")
        self.estimated_time_of_tests_by_mutant = meta.pop("estimated_durations_by_key")
        self.hash_by_function_name = meta.pop("hash_by_function_name", {})
        raw_metadata = meta.pop("mutation_metadata_by_module_name", {})
        self.mutation_metadata_by_module_name = {k: MutationMetadata.from_dict(v) for k, v in raw_metadata.items()}
        assert not meta, f"Meta file {self.meta_path} constains unexpected keys: {set(meta.keys())}"

    def register_pid(self, *, pid: int, key: str) -> None:
        """Register a process ID for tracking a mutant test."""
        self.key_by_pid[pid] = key
        self.start_time_by_pid[pid] = datetime.now()

    def register_result(self, *, pid: int, exit_code: int) -> None:
        """Register the result of a mutant test."""
        assert self.key_by_pid[pid] in self.exit_code_by_key
        key = self.key_by_pid[pid]
        self.exit_code_by_key[key] = exit_code
        self.durations_by_key[key] = (datetime.now() - self.start_time_by_pid[pid]).total_seconds()
        del self.key_by_pid[pid]
        del self.start_time_by_pid[pid]
        self.save()

    def stop_children(self) -> None:
        """Stop all child processes that are currently running tests."""
        for pid in self.key_by_pid.keys():
            os.kill(pid, signal.SIGTERM)

    def save(self) -> None:
        """Save mutation data to the meta file."""
        metadata_as_dicts = {k: v.to_dict() for k, v in self.mutation_metadata_by_module_name.items()}
        with open(self.meta_path, "w") as f:
            json.dump(
                {
                    "exit_code_by_key": self.exit_code_by_key,
                    "type_check_error_by_key": self.type_check_error_by_key,
                    "durations_by_key": self.durations_by_key,
                    "estimated_durations_by_key": self.estimated_time_of_tests_by_mutant,
                    "hash_by_function_name": self.hash_by_function_name,
                    "mutation_metadata_by_module_name": metadata_as_dicts,
                },
                f,
                indent=4,
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary for JSON storage.

        Note: Runtime state (key_by_pid, start_time_by_pid) is not serialized.
        """
        return {
            "path": str(self.path),
            "exit_code_by_key": self.exit_code_by_key,
            "durations_by_key": self.durations_by_key,
            "estimated_time_of_tests_by_mutant": self.estimated_time_of_tests_by_mutant,
            "hash_by_function_name": self.hash_by_function_name,
            "mutation_metadata_by_module_name": {
                k: v.to_dict() for k, v in self.mutation_metadata_by_module_name.items()
            },
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "SourceFileMutationData":
        """Deserialize from a dictionary.

        Note: Runtime state (key_by_pid, start_time_by_pid) is initialized empty.
        """
        instance = SourceFileMutationData(path=data["path"])
        instance.exit_code_by_key = data.get("exit_code_by_key", {})
        instance.durations_by_key = data.get("durations_by_key", {})
        instance.estimated_time_of_tests_by_mutant = data.get("estimated_time_of_tests_by_mutant", {})
        instance.hash_by_function_name = data.get("hash_by_function_name", {})
        raw_metadata = data.get("mutation_metadata_by_module_name", {})
        instance.mutation_metadata_by_module_name = {k: MutationMetadata.from_dict(v) for k, v in raw_metadata.items()}
        return instance
