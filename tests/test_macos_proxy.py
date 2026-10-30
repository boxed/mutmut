import os
import sys
import types

import pytest

from mutmut.__main__ import _pin_macos_proxy_settings


@pytest.fixture
def clean_env(monkeypatch):
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(sys, "platform", "darwin")
    return monkeypatch


def fake_scproxy(monkeypatch, proxies, exceptions=()):
    mod = types.SimpleNamespace(
        _get_proxies=lambda: proxies,
        _get_proxy_settings=lambda: {"exclude_simple": False, "exceptions": list(exceptions)},
    )
    monkeypatch.setitem(sys.modules, "_scproxy", mod)


def test_macos_system_proxy_settings_are_resolved_into_the_environment_before_forking(clean_env):
    fake_scproxy(clean_env, {})
    _pin_macos_proxy_settings()
    assert os.environ["no_proxy"] == "*"  # no system proxy: children must not query SystemConfiguration

    clean_env.delenv("no_proxy")
    fake_scproxy(clean_env, {"http": "http://proxy:3128", "https": "http://proxy:3128"}, ["*.local", "169.254/16"])
    _pin_macos_proxy_settings()
    assert os.environ["http_proxy"] == os.environ["https_proxy"] == "http://proxy:3128"
    assert os.environ["no_proxy"] == "*.local,169.254/16"


def test_explicit_proxy_environment_and_other_platforms_are_left_alone(clean_env):
    fake_scproxy(clean_env, {"http": "http://system:1"})
    clean_env.setenv("HTTPS_PROXY", "http://mine:8080")
    _pin_macos_proxy_settings()
    assert "http_proxy" not in os.environ and "no_proxy" not in os.environ

    clean_env.delenv("HTTPS_PROXY")
    clean_env.setattr(sys, "platform", "linux")
    _pin_macos_proxy_settings()
    assert not any(n.lower().endswith("_proxy") for n in os.environ)
