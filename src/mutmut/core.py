import inspect
from contextvars import ContextVar
from contextvars import Token
from typing import ClassVar

import mutmut
from mutmut.configuration import Config
from mutmut.state import state


class MutmutProgrammaticFailException(Exception):
    pass


class MutmutCallStack:
    """Async-compatible call context for dependency tracking."""

    _ctx: ClassVar[ContextVar[tuple[str | None, int]]] = ContextVar("_mutmut_call_context", default=(None, 0))

    @classmethod
    def get(cls) -> tuple[str | None, int]:
        return cls._ctx.get()

    @classmethod
    def set(cls, value: tuple[str, int]) -> Token[tuple[str | None, int]]:
        return cls._ctx.set(value)

    @classmethod
    def reset(cls, token: Token[tuple[str | None, int]]) -> None:
        cls._ctx.reset(token)


def record_trampoline_hit(name: str, caller: str | None = None) -> None:
    assert not name.startswith("src."), "Failed trampoline hit. Module name starts with `src.`, which is invalid"
    if Config.get().max_stack_depth != -1:
        f = inspect.currentframe()
        c = Config.get().max_stack_depth
        while c and f:
            filename = f.f_code.co_filename
            if "pytest" in filename or "hammett" in filename or "unittest" in filename:
                break
            f = f.f_back
            c -= 1

        if not c:
            return

    mutmut._stats.add(name)

    if caller is not None and Config.get().track_dependencies:
        state().function_dependencies[name].add(caller)
