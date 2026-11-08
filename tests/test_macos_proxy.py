import sys
import urllib.request

from mutmut.__main__ import _pin_macos_proxy_settings


def test_macos_proxy_lookups_are_answered_from_one_pre_fork_query(monkeypatch):
    calls = []
    settings = {"exclude_simple": False, "exceptions": ["*.local", "169.254/16"]}
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        urllib.request, "_get_proxies", lambda: calls.append("proxies") or {"http": "http://proxy:3128"}, raising=False
    )
    monkeypatch.setattr(
        urllib.request, "_get_proxy_settings", lambda: calls.append("settings") or settings, raising=False
    )

    _pin_macos_proxy_settings()
    for _ in range(3):  # what forked children call; none may reach SystemConfiguration again
        assert urllib.request._get_proxies() == {"http": "http://proxy:3128"}
        cached = urllib.request._get_proxy_settings()
        assert urllib.request._proxy_bypass_macosx_sysconf("build.local", cached)
        assert urllib.request._proxy_bypass_macosx_sysconf("169.254.1.2", cached)
        assert not urllib.request._proxy_bypass_macosx_sysconf("example.com", cached)
    assert calls == ["proxies", "settings"]


def test_other_platforms_are_left_alone(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(urllib.request, "_get_proxies", sentinel, raising=False)
    _pin_macos_proxy_settings()
    assert urllib.request._get_proxies is sentinel
