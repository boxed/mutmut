from __future__ import annotations

import os
from datetime import UTC, datetime
from multiprocessing import Lock
from pathlib import Path
from signal import SIGTERM

from nootnoot.app.persistence import MetaPayload, load_meta, save_meta


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


START_TIMES_BY_PID_LOCK = Lock()


class SourceFileMutationData:
    def __init__(self, *, path: Path):
        self.estimated_time_of_tests_by_mutant: dict[str, float] = {}
        self.path = path
        self.meta_path = Path("mutants") / (str(path) + ".meta")
        self.key_by_pid: dict[int, str] = {}
        self.exit_code_by_key: dict[str, int | None] = {}
        self.durations_by_key: dict[str, float] = {}
        self.start_time_by_pid: dict[int, datetime] = {}

    def load(self, *, debug: bool = False) -> None:
        payload = load_meta(self.meta_path, debug=debug)
        if payload is None:
            return
        self.exit_code_by_key = payload.exit_code_by_key
        self.durations_by_key = payload.durations_by_key
        self.estimated_time_of_tests_by_mutant = payload.estimated_durations_by_key

    def register_pid(self, *, pid: int, key: str) -> None:
        self.key_by_pid[pid] = key
        with START_TIMES_BY_PID_LOCK:
            self.start_time_by_pid[pid] = _utcnow()

    def register_result(self, *, pid: int, exit_code: int | None) -> None:
        key = self.key_by_pid.get(pid)
        if key not in self.exit_code_by_key:
            msg = f"Unknown mutant key for pid {pid}"
            raise KeyError(msg)
        self.exit_code_by_key[key] = exit_code
        self.durations_by_key[key] = (_utcnow() - self.start_time_by_pid[pid]).total_seconds()
        del self.key_by_pid[pid]
        with START_TIMES_BY_PID_LOCK:
            del self.start_time_by_pid[pid]
        self.save()

    def stop_children(self) -> None:
        for pid in self.key_by_pid:
            os.kill(pid, SIGTERM)

    def save(self) -> None:
        save_meta(
            self.meta_path,
            MetaPayload(
                exit_code_by_key=self.exit_code_by_key,
                durations_by_key=self.durations_by_key,
                estimated_durations_by_key=self.estimated_time_of_tests_by_mutant,
            ),
        )
