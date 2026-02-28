import json
import os
import signal
from datetime import datetime
from pathlib import Path


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

    def load(self) -> None:
        try:
            with open(self.meta_path) as f:
                meta = json.load(f)
        except FileNotFoundError:
            return

        self.exit_code_by_key = meta.pop("exit_code_by_key")
        self.type_check_error_by_key = meta.pop("type_check_error_by_key", {})
        self.durations_by_key = meta.pop("durations_by_key")
        self.estimated_time_of_tests_by_mutant = meta.pop("estimated_durations_by_key")
        assert not meta, f"Meta file {self.meta_path} constains unexpected keys: {set(meta.keys())}"

    def register_pid(self, *, pid: int, key: str) -> None:
        self.key_by_pid[pid] = key
        self.start_time_by_pid[pid] = datetime.now()

    def register_result(self, *, pid: int, exit_code: int) -> None:
        assert self.key_by_pid[pid] in self.exit_code_by_key
        key = self.key_by_pid[pid]
        self.exit_code_by_key[key] = exit_code
        self.durations_by_key[key] = (datetime.now() - self.start_time_by_pid[pid]).total_seconds()
        # TODO: maybe rate limit this? Saving on each result can slow down mutation testing a lot if the test run is fast.
        del self.key_by_pid[pid]
        del self.start_time_by_pid[pid]
        self.save()

    def stop_children(self) -> None:
        for pid in self.key_by_pid.keys():
            os.kill(pid, signal.SIGTERM)

    def save(self) -> None:
        with open(self.meta_path, "w") as f:
            json.dump(
                {
                    "exit_code_by_key": self.exit_code_by_key,
                    "type_check_error_by_key": self.type_check_error_by_key,
                    "durations_by_key": self.durations_by_key,
                    "estimated_durations_by_key": self.estimated_time_of_tests_by_mutant,
                },
                f,
                indent=4,
            )
