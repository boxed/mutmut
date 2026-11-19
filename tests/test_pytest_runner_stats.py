"""The stats collector must ignore the setup and teardown report durations (#544)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import mutmut
from mutmut.__main__ import PytestRunner


def test_stats_collector_records_only_the_call_phase(tmp_path, monkeypatch):
    # The collector is a class local to run_stats(); intercept the plugin that
    # run_stats() hands to pytest instead of running pytest, then feed the hooks
    # synthetic reports so the assertion is about the guard, not about timing.
    captured = []

    def fake_execute_pytest(self, params, **kwargs):
        captured.extend(kwargs["plugins"])
        return 0

    monkeypatch.setattr(PytestRunner, "execute_pytest", fake_execute_pytest)
    (tmp_path / "src").mkdir()  # mutmut's config discovery needs a source dir to exist
    (tmp_path / "mutants").mkdir()
    monkeypatch.chdir(tmp_path)
    mutmut._reset_globals()
    try:
        PytestRunner().run_stats(tests=[])
        (collector,) = captured

        nodeid = "test_example.py::test_fast"
        item = SimpleNamespace(nodeid=nodeid)
        collector.pytest_runtest_logstart(nodeid, location=None)
        for when, duration in (("setup", 0.4), ("call", 0.01), ("teardown", 0.5)):
            collector.pytest_runtest_makereport(item, SimpleNamespace(when=when, duration=duration))

        assert mutmut.duration_by_test[nodeid] == pytest.approx(0.01)
    finally:
        mutmut._reset_globals()
