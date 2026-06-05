from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field


@dataclass
class MutmutState:
    old_function_hashes: dict[str, str] = field(default_factory=dict)
    current_function_hashes: dict[str, str] = field(default_factory=dict)
    function_dependencies: defaultdict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


_state: MutmutState | None = None


def state() -> MutmutState:
    global _state
    if _state is None:
        _state = MutmutState()
    return _state


def reset_state() -> None:
    global _state
    _state = None
