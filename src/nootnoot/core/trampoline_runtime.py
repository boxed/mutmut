from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


class _TrampolineHooks:
    def __init__(self) -> None:
        self.get_max_stack_depth: Callable[[], int] | None = None
        self.add_stat: Callable[[str], None] | None = None


_trampoline_hooks = _TrampolineHooks()


class NootNootProgrammaticFailException(Exception):
    pass


def register_trampoline_hooks(
    *,
    get_max_stack_depth: Callable[[], int] | None,
    add_stat: Callable[[str], None] | None,
) -> None:
    _trampoline_hooks.get_max_stack_depth = get_max_stack_depth
    _trampoline_hooks.add_stat = add_stat


def record_trampoline_hit(name: str) -> None:
    if name.startswith("src."):
        msg = "Failed trampoline hit. Module name starts with `src.`, which is invalid"
        raise ValueError(msg)
    get_max_stack_depth = _trampoline_hooks.get_max_stack_depth
    add_stat = _trampoline_hooks.add_stat
    if get_max_stack_depth is None or add_stat is None:
        return
    max_stack_depth = int(get_max_stack_depth())
    if max_stack_depth != -1:
        f = inspect.currentframe()
        c = max_stack_depth
        while c and f:
            filename = f.f_code.co_filename
            if "pytest" in filename or "hammett" in filename or "unittest" in filename:
                break
            f = f.f_back
            c -= 1

        if not c:
            return

    add_stat(name)
