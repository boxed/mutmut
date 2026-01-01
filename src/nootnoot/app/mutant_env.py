from __future__ import annotations

import os
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

MUTANT_UNDER_TEST_ENV_VAR = "MUTANT_UNDER_TEST"


def set_mutant_under_test(value: str) -> None:
    """Set the mutation-test selector for the current process.

    This is intentionally environment-based so it naturally propagates to:
      - async tasks (same process)
      - threads (same process)
      - child processes (inherited env by default)
    """
    os.environ[MUTANT_UNDER_TEST_ENV_VAR] = value


def clear_mutant_under_test() -> None:
    os.environ.pop(MUTANT_UNDER_TEST_ENV_VAR, None)


@contextmanager
def mutant_under_test(value: str) -> Iterator[None]:
    """Temporarily set MUTANT_UNDER_TEST and restore the previous value.

    Prefer this for scoped operations (stats, clean runs, forced-fail runs) to keep
    nootnoot behavior deterministic and test-friendly.
    """
    old = os.environ.get(MUTANT_UNDER_TEST_ENV_VAR)
    os.environ[MUTANT_UNDER_TEST_ENV_VAR] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(MUTANT_UNDER_TEST_ENV_VAR, None)
        else:
            os.environ[MUTANT_UNDER_TEST_ENV_VAR] = old
