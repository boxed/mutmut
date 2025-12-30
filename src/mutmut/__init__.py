from __future__ import annotations

import importlib.metadata
from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mutmut.__main__ import Config

__version__ = importlib.metadata.version("mutmut")


duration_by_test: defaultdict[str, float] = defaultdict(float)
stats_time: float | None = None
config: Config | None = None

_stats = set()
tests_by_mangled_function_name = defaultdict(set)
_covered_lines: dict[str, set[int]] | None = None


def add_stat(name: str) -> None:
    _stats.add(name)


def clear_stats() -> None:
    _stats.clear()


def iter_stats() -> set[str]:
    return set(_stats)


def consume_stats() -> set[str]:
    stats = set(_stats)
    _stats.clear()
    return stats


def set_covered_lines(covered_lines: dict[str, set[int]] | None) -> None:
    globals()["_covered_lines"] = covered_lines


def get_covered_lines() -> dict[str, set[int]] | None:
    return _covered_lines


def _reset_globals():
    module_globals = globals()
    duration_by_test.clear()
    module_globals["stats_time"] = None
    module_globals["config"] = None
    module_globals["_stats"] = set()
    module_globals["tests_by_mangled_function_name"] = defaultdict(set)
    module_globals["_covered_lines"] = None
