"""Tests for the status line printer's throttle."""

import io
import sys
from datetime import datetime

import pytest

from mutmut.ui import terminal

START = datetime(1970, 1, 1)


class FakeClock(datetime):
    """A datetime whose now() the test moves by hand."""

    current = START

    @classmethod
    def now(cls, tz=None):
        return cls.current


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    """Hold the printer's clock at START; a test moves it by setting clock.current."""
    FakeClock.current = START
    monkeypatch.setattr(terminal, "datetime", FakeClock)
    return FakeClock


@pytest.fixture
def out(monkeypatch):
    buffer = io.StringIO()
    # print_status writes to sys.__stdout__, past capsys (which only swaps
    # sys.stdout), so this captures output by replacing sys.__stdout__ itself
    monkeypatch.setattr(sys, "__stdout__", buffer)
    return buffer


def test_a_second_update_within_the_interval_is_not_printed(out):
    """Verify that updates are throttled to once per interval."""
    p = terminal.status_printer()
    p("first")
    p("second")
    assert "first" in out.getvalue()
    assert "second" not in out.getvalue()


def test_a_throttled_callable_is_not_called(out):
    """Verify that a status line passed as a callable is only built when it will be printed."""
    p = terminal.status_printer()
    calls = []

    def line():
        calls.append(1)
        return "built"

    p(line)
    p(line)
    assert len(calls) == 1


def test_force_output_prints_within_the_interval(out):
    """Verify that force_output bypasses the update interval limit."""
    p = terminal.status_printer()
    p("first")
    p(lambda: "forced", force_output=True)
    assert "forced" in out.getvalue()
