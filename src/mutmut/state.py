"""Runtime state for dependency tracking in mutmut.

This module provides a singleton-pattern state object for tracking function hashes
and dependencies across mutmut runs. The state is persisted to mutmut-stats.json
and restored on subsequent runs.
"""

from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field


@dataclass
class MutmutState:
    """Runtime state for dependency tracking.

    Attributes:
        old_function_hashes: Function hashes from the previous run (loaded from JSON).
            Used to detect which functions changed between runs.
        current_function_hashes: Function hashes from the current run (populated during
            mutant generation). Saved to JSON at end of run.
        function_dependencies: Maps callee function names to the set of caller function
            names. Used to propagate test coverage through call chains.
    """

    # Hashes from previous run (loaded from JSON)
    old_function_hashes: dict[str, str] = field(default_factory=dict)

    # Hashes from current run (populated during mutant generation)
    current_function_hashes: dict[str, str] = field(default_factory=dict)

    # callee -> set of callers
    function_dependencies: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


_state: MutmutState | None = None


def state() -> MutmutState:
    """Get the global MutmutState singleton, creating it if needed."""
    global _state
    if _state is None:
        _state = MutmutState()
    return _state


def reset_state() -> None:
    """Reset the global state. Primarily used for testing."""
    global _state
    _state = None
