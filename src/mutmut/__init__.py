from __future__ import annotations

import importlib.metadata
import warnings

from mutmut.configuration import config
from mutmut.configuration import reset_config
from mutmut.state import reset_state
from mutmut.state import state

__version__ = importlib.metadata.version("mutmut")


_DEPRECATED_STATE_ATTRS = frozenset(
    {
        "stats_time",
        "duration_by_test",
        "tests_by_mangled_function_name",
        "_stats",
        "_covered_lines",
        "_excluded_lines",
    }
)


def __getattr__(name: str) -> object:
    match name:
        case "config":
            warnings.warn(
                "mutmut.config is deprecated as of 3.4.1, use mutmut.configuration.config() instead",
                FutureWarning,
                stacklevel=2,
            )
            return config()
        case name if name in _DEPRECATED_STATE_ATTRS:
            warnings.warn(
                f"mutmut.{name} is deprecated, use mutmut.state.state().{name} instead",
                FutureWarning,
                stacklevel=2,
            )
            return getattr(state(), name)
        case _:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reset_globals() -> None:
    reset_config()
    reset_state()
