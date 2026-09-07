from typing import Any

import pytest

import mutmut.configuration


@pytest.fixture(autouse=True)
def reset_config():
    mutmut.configuration.reset_config()


@pytest.fixture(name="patch_config")
def monkeypatch_config_get(monkeypatch):
    """Utility to overwrite values in the loaded Config.

    Mutates the singleton instance in place (rather than patching the ``config()``
    accessor) so the change is visible to every module that already imported
    ``config`` by reference (``from mutmut.configuration import config``).
    """

    def patch_config(config_name: str, value: Any):
        cfg = mutmut.configuration.config()
        assert hasattr(cfg, config_name)
        monkeypatch.setattr(cfg, config_name, value)

    return patch_config
