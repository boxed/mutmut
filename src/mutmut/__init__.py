from __future__ import annotations

import importlib.metadata
import warnings
from collections import defaultdict

from mutmut.configuration import Config
from mutmut.state import reset_state

__version__ = importlib.metadata.version("mutmut")


stats_time: float | None = None
duration_by_test: dict[str, float] = defaultdict(float)
tests_by_mangled_function_name: dict[str, set[str]] = defaultdict(set)

_stats: set[str] = set()
_covered_lines: dict[str, set[int]] | None = None


def __getattr__(name: str) -> object:
    match name:
        case "config":
            warnings.warn(
                "mutmut.config is deprecated as of 3.4.1, use mutmut.configuration.Config.get() instead",
                FutureWarning,
                stacklevel=2,
            )
            return Config.get()
        case _:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reset_globals() -> None:
    global duration_by_test, stats_time, _stats, tests_by_mangled_function_name
    global _covered_lines

    duration_by_test.clear()
    stats_time = None
    Config.reset()
    _stats = set()
    tests_by_mangled_function_name = defaultdict(set)
    _covered_lines = None
    reset_state()
