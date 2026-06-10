from contextvars import ContextVar
from contextvars import Token
from typing import ClassVar


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
