from __future__ import annotations

import importlib.metadata

from nootnoot.state import NootNootState, get_state, set_state

__version__ = importlib.metadata.version("nootnoot")


def add_stat(name: str) -> None:
    get_state().add_stat(name)


def clear_stats() -> None:
    get_state().clear_stats()


def iter_stats() -> set[str]:
    return get_state().iter_stats()


def consume_stats() -> set[str]:
    return get_state().consume_stats()


def set_covered_lines(covered_lines: dict[str, set[int]] | None) -> None:
    get_state().covered_lines = covered_lines


def get_covered_lines() -> dict[str, set[int]] | None:
    return get_state().covered_lines


def _reset_globals():
    set_state(NootNootState())
