from __future__ import annotations

import pytest

from nootnoot.state import NootNootState, reset_state, set_state


@pytest.fixture
def nootnoot_state() -> NootNootState:
    state = NootNootState()
    token = set_state(state)
    try:
        yield state
    finally:
        reset_state(token)
