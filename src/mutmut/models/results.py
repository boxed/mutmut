"""Result data models for worker/orchestrator communication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StatsResult:
    """Stats collected by a forked child, serialized back to the parent.

    The hot-fork runner collects stats inside a forked child (so the parent
    never imports pytest). The child cannot mutate the parent's ``state()``
    directly, so it packs the collected data into this picklable structure and
    the parent merges it back in.
    """

    exit_code: int
    tests_by_mangled_function_name: dict[str, set[str]]
    duration_by_test: dict[str, float]
    stats_time: float
    function_dependencies: dict[str, set[str]]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a picklable dict (sets become lists)."""
        return {
            "exit_code": self.exit_code,
            "tests_by_mangled_function_name": {k: list(v) for k, v in self.tests_by_mangled_function_name.items()},
            "duration_by_test": self.duration_by_test,
            "stats_time": self.stats_time,
            "function_dependencies": {k: list(v) for k, v in self.function_dependencies.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatsResult:
        """Deserialize from the dict produced by :meth:`to_dict`."""
        return cls(
            exit_code=data["exit_code"],
            tests_by_mangled_function_name={k: set(v) for k, v in data["tests_by_mangled_function_name"].items()},
            duration_by_test=data["duration_by_test"],
            stats_time=data["stats_time"],
            function_dependencies={k: set(v) for k, v in data["function_dependencies"].items()},
        )
