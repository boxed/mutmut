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

_stats: set[str] = set()
tests_by_mangled_function_name: defaultdict[str, set[str]] = defaultdict(set)
_covered_lines: dict[str, set[int]] | None = None


def _reset_globals() -> None:
    global duration_by_test, stats_time, config, _stats, tests_by_mangled_function_name
    global _covered_lines

    duration_by_test.clear()
    stats_time = None
    config = None
    _stats = set()
    tests_by_mangled_function_name = defaultdict(set)
    _covered_lines = None
