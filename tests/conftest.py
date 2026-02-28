import pytest

from mutmut.configuration import config
from mutmut.configuration import reset_config
from mutmut.state import reset_state


def reset_singletons():
    """Reset configuration and state singletons."""
    reset_config()
    reset_state()


@pytest.fixture(autouse=True)
def reset_singletons_fixture():
    """Reset state before and after each test."""
    reset_singletons()
    yield
    reset_singletons()


@pytest.fixture()
def patch_config():
    def _patch_config(name, value):
        cfg = config()
        assert hasattr(cfg, name)
        setattr(cfg, name, value)

    return _patch_config
