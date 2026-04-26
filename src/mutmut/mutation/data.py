import json
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

from mutmut.mutation.file_mutation import MutationMetadata


class SourceFileMutationData:
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
        self.key_by_pid[pid] = key
        self.start_time_by_pid[pid] = datetime.now()

    def register_result(self, *, pid: int, exit_code: int) -> None:
        assert self.key_by_pid[pid] in self.exit_code_by_key
        key = self.key_by_pid[pid]
        self.exit_code_by_key[key] = exit_code
        self.durations_by_key[key] = (datetime.now() - self.start_time_by_pid[pid]).total_seconds()
        del self.key_by_pid[pid]
        del self.start_time_by_pid[pid]
        self.save()

    def stop_children(self) -> None:
        for pid in self.key_by_pid.keys():
            os.kill(pid, signal.SIGTERM)

    def save(self) -> None:
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
