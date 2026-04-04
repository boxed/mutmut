import pytest

from mutmut import Config


@pytest.fixture(autouse=True)
def reset_config():
    Config.reset()
