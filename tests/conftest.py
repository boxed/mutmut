from typing import Any

import pytest

import mutmut.configuration


@pytest.fixture(autouse=True)
def reset_config():
    mutmut.configuration.Config.reset()


@pytest.fixture(name="patch_config")
def monkeypatch_config_get(monkeypatch):
    """Utility to overwrite values in the loaded Config"""
    orig_get = mutmut.configuration.Config.get

    def patch_config(config_name: str, value: Any):
        def patched_get():
            config = orig_get()
            assert hasattr(config, config_name)
            setattr(config, config_name, value)
            return config

        monkeypatch.setattr(mutmut.configuration.Config, "get", patched_get)

    return patch_config
