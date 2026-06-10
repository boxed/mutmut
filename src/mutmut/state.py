from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field


@dataclass
class MutmutState:
    old_function_hashes: dict[str, str] = field(default_factory=dict)
    current_function_hashes: dict[str, str] = field(default_factory=dict)
    function_dependencies: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Fingerprints loaded from the previous run, used to detect config / dependency
    # changes the per-function source hashes cannot see. Empty when absent (pre-upgrade
    # cache or first run), in which case no invalidation is triggered.
    old_config_fingerprint: dict[str, str] = field(default_factory=dict)
    # Change-detection baselines describe the state at the *last full run*. The ``old_``
    # values are what we compare against; the others are what gets persisted (only
    # refreshed on a full run, so a ``warn`` keeps firing until the cache is rebuilt).
    old_watched_file_hashes: dict[str, str] = field(default_factory=dict)
    watched_file_hashes: dict[str, str] = field(default_factory=dict)
    old_git_commit: str | None = None
    git_commit: str | None = None


_state: MutmutState | None = None


def state() -> MutmutState:
    global _state
    if _state is None:
        _state = MutmutState()
    return _state


def reset_state() -> None:
    global _state
    _state = None
