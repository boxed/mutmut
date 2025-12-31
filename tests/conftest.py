from __future__ import annotations

import pytest

from mutmut.state import MutmutState, reset_state, set_state


@pytest.fixture
def mutmut_state() -> MutmutState:
    state = MutmutState()
    token = set_state(state)
    try:
        yield state
    finally:
        reset_state(token)
