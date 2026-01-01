from __future__ import annotations

import json
import os
import warnings
from collections import defaultdict
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nootnoot.app.state import NootNootState

SCHEMA_VERSION = 1


@dataclass
class MetaPayload:
    exit_code_by_key: dict[str, int | None]
    durations_by_key: dict[str, float]
    estimated_durations_by_key: dict[str, float]


def _warn_debug(*, debug: bool, message: str) -> None:
    if debug:
        warnings.warn(message, stacklevel=2)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, JSONDecodeError):
        return None


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)
        file.flush()
        os.fsync(file.fileno())
    Path(tmp_path).replace(path)


def _pop_schema_version(data: dict[str, Any], *, path: Path, debug: bool) -> int:
    schema_version = int(data.pop("schema_version", 0))
    if schema_version > SCHEMA_VERSION:
        _warn_debug(
            debug=debug,
            message=f"{path} schema_version {schema_version} is newer than supported {SCHEMA_VERSION}",
        )
    return schema_version


def _warn_on_unknown_keys(data: dict[str, Any], *, path: Path, debug: bool) -> None:
    if not data:
        return
    unexpected = ", ".join(sorted(data.keys()))
    _warn_debug(debug=debug, message=f"{path} contains unexpected keys: {unexpected}")


def load_meta(path: Path, *, debug: bool) -> MetaPayload | None:
    data = _read_json(path)
    if data is None:
        return None
    _pop_schema_version(data, path=path, debug=debug)
    try:
        exit_code_by_key = data.pop("exit_code_by_key")
        durations_by_key = data.pop("durations_by_key")
        estimated_durations_by_key = data.pop("estimated_durations_by_key")
    except KeyError as exc:
        msg = f"Meta file {path} is missing required keys"
        raise ValueError(msg) from exc
    _warn_on_unknown_keys(data, path=path, debug=debug)
    return MetaPayload(
        exit_code_by_key=exit_code_by_key,
        durations_by_key=durations_by_key,
        estimated_durations_by_key=estimated_durations_by_key,
    )


def save_meta(path: Path, payload: MetaPayload) -> None:
    _write_json_atomic(
        path,
        dict(
            schema_version=SCHEMA_VERSION,
            exit_code_by_key=payload.exit_code_by_key,
            durations_by_key=payload.durations_by_key,
            estimated_durations_by_key=payload.estimated_durations_by_key,
        ),
    )


def load_stats(state: NootNootState) -> bool:
    data = _read_json(Path("mutants/nootnoot-stats.json"))
    if data is None:
        return False
    debug = state.config is not None and state.config.debug
    _pop_schema_version(data, path=Path("mutants/nootnoot-stats.json"), debug=debug)
    try:
        tests_by_mangled_function_name = data.pop("tests_by_mangled_function_name")
        duration_by_test = data.pop("duration_by_test")
        stats_time = data.pop("stats_time")
    except KeyError as exc:
        msg = "Stats file is missing required keys"
        raise ValueError(msg) from exc
    _warn_on_unknown_keys(data, path=Path("mutants/nootnoot-stats.json"), debug=debug)
    for k, v in tests_by_mangled_function_name.items():
        state.tests_by_mangled_function_name[k] |= set(v)
    state.duration_by_test = defaultdict(float, duration_by_test)
    state.stats_time = stats_time
    return True


def save_stats(state: NootNootState) -> None:
    _write_json_atomic(
        Path("mutants/nootnoot-stats.json"),
        dict(
            schema_version=SCHEMA_VERSION,
            tests_by_mangled_function_name={
                k: list(v) for k, v in state.tests_by_mangled_function_name.items()
            },
            duration_by_test=state.duration_by_test,
            stats_time=state.stats_time,
        ),
    )
