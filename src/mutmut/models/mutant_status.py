"""Mutant status enum for mutation testing results."""

from enum import Enum
from typing import NamedTuple


class Status(NamedTuple):
    text: str
    emoji: str


class MutantStatus(Enum):
    """Result status for a tested mutant."""

    KILLED = Status(text="killed", emoji="🎉")
    SURVIVED = Status(text="survived", emoji="🙁")
    TIMEOUT = Status(text="timeout", emoji="⏰")
    NO_TESTS = Status(text="no tests", emoji="🫥")
    SKIPPED = Status(text="skipped", emoji="🔇")
    SUSPICIOUS = Status(text="suspicious", emoji="🤔")
    SEGFAULT = Status(text="segfault", emoji="💥")
    TYPECHECK = Status(text="caught by type check", emoji="🧙")
    CHECK_INTERRUPTED_BY_USER = Status(text="check was interrupted by user", emoji="🛑")
    NOT_CHECKED = Status(text="not checked", emoji="?")

    @classmethod
    def from_exit_code(cls, exit_code: int | None) -> "MutantStatus":
        """Convert a test-runner exit code to a MutantStatus."""
        match exit_code:
            case None:
                return cls.NOT_CHECKED
            case 0:
                return cls.SURVIVED
            case 1 | 3:
                return cls.KILLED
            case 5 | 33:
                return cls.NO_TESTS
            case 34:
                return cls.SKIPPED
            case 2:
                return cls.CHECK_INTERRUPTED_BY_USER
            case 35:
                return cls.SUSPICIOUS
            case 36 | -24 | 24 | 152 | 255:
                return cls.TIMEOUT
            case -11 | -9:
                return cls.SEGFAULT
            case 37:
                return cls.TYPECHECK
            case _:
                return cls.SUSPICIOUS

    @property
    def text(self) -> str:
        return self.value.text

    @property
    def emoji(self) -> str:
        return self.value.emoji
