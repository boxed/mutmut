import sys
import threading
from contextvars import ContextVar
from contextvars import Token
from typing import ClassVar

# Mitigation for #596. On CPython < 3.12 the cyclic GC can run while ContextVar.set()/reset() is allocating. A garbage
# object whose (trampolined) __del__ is finalized at that point touches the same ContextVar while it is half updated,
# which is believed to corrupt it (see python/cpython#148891) and was observed to segfault stats collection. The
# version gate is our best estimate of where this stops happening, not a verified boundary. The GC runs finalizers on
# the thread that triggered it, so a
# per-thread flag is enough to detect that case without touching any process-wide GC state. While the flag is set,
# get() reports "no caller" and set()/reset() do nothing, so such a finalizer is simply not tracked.
_GUARD_REENTRANCY = sys.version_info < (3, 12)


class MutmutCallStack:
    """Async-compatible call context for dependency tracking."""

    _ctx: ClassVar[ContextVar[tuple[str | None, int]]] = ContextVar("_mutmut_call_context", default=(None, 0))
    _busy: ClassVar[threading.local] = threading.local()

    @classmethod
    def get(cls) -> tuple[str | None, int]:
        if _GUARD_REENTRANCY and getattr(cls._busy, "active", False):
            return (None, 0)
        return cls._ctx.get()

    @classmethod
    def set(cls, value: tuple[str, int]) -> Token[tuple[str | None, int]] | None:
        """Returns None, leaving the context unchanged, if called from a finalizer that interrupted set()/reset()
        on this thread. reset(None) is a no-op."""
        if not _GUARD_REENTRANCY:
            return cls._ctx.set(value)
        busy = cls._busy
        if getattr(busy, "active", False):
            return None
        busy.active = True
        try:
            return cls._ctx.set(value)
        finally:
            busy.active = False

    @classmethod
    def reset(cls, token: Token[tuple[str | None, int]] | None) -> None:
        if token is None:
            return
        if not _GUARD_REENTRANCY:
            cls._ctx.reset(token)
            return
        busy = cls._busy
        if getattr(busy, "active", False):
            return
        busy.active = True
        try:
            cls._ctx.reset(token)
        finally:
            busy.active = False


class MutmutProgrammaticFailException(Exception):
    """Raised by the trampoline when the ``fail`` mutant is active."""
