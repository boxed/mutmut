from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from json import JSONDecodeError
from multiprocessing import Lock
from pathlib import Path
from signal import SIGTERM

import mutmut


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
        self.hash_by_function_name: dict[str, str] = {}
        self.start_time_by_pid: dict[int, datetime] = {}

    def load(self) -> None:
        try:
            with Path(self.meta_path).open(encoding="utf-8") as f:
                meta = json.load(f)
        except FileNotFoundError:
            return

        self.exit_code_by_key = meta.pop("exit_code_by_key")
        self.hash_by_function_name = meta.pop("hash_by_function_name")
        self.durations_by_key = meta.pop("durations_by_key")
        self.estimated_time_of_tests_by_mutant = meta.pop("estimated_durations_by_key")
        if meta:
            unexpected = ", ".join(sorted(meta.keys()))
            msg = f"Meta file {self.meta_path} contains unexpected keys: {unexpected}"
            raise ValueError(msg)

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
        with Path(self.meta_path).open("w", encoding="utf-8") as f:
            json.dump(
                dict(
                    exit_code_by_key=self.exit_code_by_key,
                    hash_by_function_name=self.hash_by_function_name,
                    durations_by_key=self.durations_by_key,
                    estimated_durations_by_key=self.estimated_time_of_tests_by_mutant,
                ),
                f,
                indent=4,
            )


def load_stats() -> bool:
    did_load = False
    try:
        with Path("mutants/mutmut-stats.json").open(encoding="utf-8") as f:
            data = json.load(f)
            for k, v in data.pop("tests_by_mangled_function_name").items():
                mutmut.tests_by_mangled_function_name[k] |= set(v)
            mutmut.duration_by_test = defaultdict(float, data.pop("duration_by_test"))
            mutmut.stats_time = data.pop("stats_time")
            if data:
                msg = f"Unexpected keys in stats file: {sorted(data.keys())}"
                raise ValueError(msg)
            did_load = True
    except (FileNotFoundError, JSONDecodeError):
        pass
    return did_load


def save_stats() -> None:
    with Path("mutants/mutmut-stats.json").open("w", encoding="utf-8") as f:
        json.dump(
            dict(
                tests_by_mangled_function_name={
                    k: list(v) for k, v in mutmut.tests_by_mangled_function_name.items()
                },
                duration_by_test=mutmut.duration_by_test,
                stats_time=mutmut.stats_time,
            ),
            f,
            indent=4,
        )
