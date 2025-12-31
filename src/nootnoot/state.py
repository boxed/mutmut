from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from nootnoot.config import Config


@dataclass
class NootNootState:
    duration_by_test: defaultdict[str, float] = field(default_factory=lambda: defaultdict(float))
    tests_by_mangled_function_name: defaultdict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    stats_time: float | None = None
    config: Config | None = None
    covered_lines: dict[str, set[int]] | None = None
    stats: set[str] = field(default_factory=set)

    def add_stat(self, name: str) -> None:
        self.stats.add(name)

    def clear_stats(self) -> None:
        self.stats.clear()

    def iter_stats(self) -> set[str]:
        return set(self.stats)

    def consume_stats(self) -> set[str]:
        stats = set(self.stats)
        self.stats.clear()
        return stats


_state_var: ContextVar[NootNootState | None] = ContextVar("nootnoot_state", default=None)


def get_state() -> NootNootState:
    state = _state_var.get()
    if state is None:
        msg = "NootNoot state is not initialized"
        raise RuntimeError(msg)
    return state


def set_state(state: NootNootState) -> Token[NootNootState | None]:
    return _state_var.set(state)


def reset_state(token: Token[NootNootState | None]) -> None:
    _state_var.reset(token)


@contextmanager
def using_state(state: NootNootState) -> Iterator[NootNootState]:
    token = set_state(state)
    try:
        yield state
    finally:
        reset_state(token)
