from __future__ import annotations

import importlib.metadata
import warnings

from mutmut.configuration import config as configuration_config
from mutmut.state import state

__version__ = importlib.metadata.version("mutmut")


# DEPRECATED: The following module-level globals have been moved to MutmutState.
# Access via mutmut.<name> will emit a FutureWarning and redirect to state().<name>.
# - stats_time
# - duration_by_test
# - tests_by_mangled_function_name
# - _stats
# - _covered_lines


def __getattr__(name: str) -> object:
    match name:
        case "config":
            warnings.warn(
                "Accessing mutmut.config is deprecated as of 3.4.1, use mutmut.configuration.config() instead",
                FutureWarning,
                stacklevel=2,
            )
            return configuration_config()
        case "stats_time" | "duration_by_test" | "tests_by_mangled_function_name" | "_stats" | "_covered_lines":
            warnings.warn(
                f"Accessing mutmut.{name} is deprecated as of 3.5.2. Use mutmut.state.state().{name} instead.",
                FutureWarning,
                stacklevel=2,
            )
            return getattr(state(), name)
        case _:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
