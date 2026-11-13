"""
Tests for the re-entrancy guard in MutmutCallStack (#596).

On CPython < 3.12 the cyclic GC can run a finalizer while ContextVar.set()/reset() is allocating. If that finalizer is
a trampolined function it touches the half-updated ContextVar and can corrupt it. The guard makes such a finalizer a
no-op for call tracking. The unit tests simulate the interrupting finalizer deterministically with a fake ContextVar.
"""

import gc
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from mutmut import core
from mutmut.core import MutmutCallStack


class FakeContextVar:
    """Stands in for MutmutCallStack._ctx and runs `interrupt` in the middle of set()/reset(), like a GC finalizer."""

    def __init__(self, interrupt=None):
        self.interrupt = interrupt
        self.calls: list[str] = []
        self.value = (None, 0)

    def _maybe_interrupt(self):
        interrupt, self.interrupt = self.interrupt, None  # only interrupt once
        if interrupt is not None:
            interrupt()

    def get(self):
        self.calls.append("get")
        return self.value

    def set(self, value):
        self.calls.append("set")
        self._maybe_interrupt()
        self.value = value
        return f"token:{value}"

    def reset(self, token):
        self.calls.append("reset")
        self._maybe_interrupt()
        self.value = (None, 0)


@pytest.fixture
def guard_on(monkeypatch):
    monkeypatch.setattr(core, "_GUARD_REENTRANCY", True)


def install(monkeypatch, fake):
    monkeypatch.setattr(MutmutCallStack, "_ctx", fake)


def test_set_get_reset_roundtrip_with_real_contextvar(guard_on):
    assert MutmutCallStack.get() == (None, 0)
    token = MutmutCallStack.set(("a", 1))
    assert token is not None
    assert MutmutCallStack.get() == ("a", 1)
    MutmutCallStack.reset(token)
    assert MutmutCallStack.get() == (None, 0)


def test_finalizer_interrupting_set_does_not_touch_the_contextvar(monkeypatch, guard_on):
    seen = {}

    def finalizer():
        seen["get"] = MutmutCallStack.get()
        seen["set"] = MutmutCallStack.set(("nested", 9))
        MutmutCallStack.reset(seen["set"])

    fake = FakeContextVar(interrupt=finalizer)
    install(monkeypatch, fake)

    token = MutmutCallStack.set(("outer", 1))

    assert seen == {"get": (None, 0), "set": None}
    assert fake.calls == ["set"], "the nested get/set/reset must not reach the ContextVar"
    assert token == "token:('outer', 1)"
    assert fake.value == ("outer", 1)


def test_finalizer_interrupting_reset_does_not_touch_the_contextvar(monkeypatch, guard_on):
    seen = {}

    def finalizer():
        seen["get"] = MutmutCallStack.get()
        seen["set"] = MutmutCallStack.set(("nested", 9))
        MutmutCallStack.reset(seen["set"])

    fake = FakeContextVar()
    install(monkeypatch, fake)
    token = MutmutCallStack.set(("outer", 1))
    fake.calls.clear()
    fake.interrupt = finalizer

    MutmutCallStack.reset(token)

    assert seen == {"get": (None, 0), "set": None}
    assert fake.calls == ["reset"]
    assert fake.value == (None, 0)


def test_reset_with_a_token_from_inside_an_interrupting_finalizer_is_skipped(monkeypatch, guard_on):
    """Defensive: even a real token must not reach ContextVar.reset() while this thread is inside set()/reset()."""
    fake = FakeContextVar(interrupt=lambda: MutmutCallStack.reset("token:from-elsewhere"))
    install(monkeypatch, fake)

    MutmutCallStack.set(("outer", 1))

    assert fake.calls == ["set"]


def test_reset_none_is_a_noop(monkeypatch, guard_on):
    fake = FakeContextVar()
    install(monkeypatch, fake)

    MutmutCallStack.reset(None)

    assert fake.calls == []


def test_flag_is_cleared_when_set_raises(monkeypatch, guard_on):
    class Boom(Exception):
        pass

    def boom():
        raise Boom

    fake = FakeContextVar(interrupt=boom)
    install(monkeypatch, fake)

    with pytest.raises(Boom):
        MutmutCallStack.set(("x", 1))

    # a later call on the same thread must work normally again
    assert MutmutCallStack.set(("y", 2)) == "token:('y', 2)"
    assert MutmutCallStack.get() == ("y", 2)


def test_flag_is_cleared_when_reset_raises(monkeypatch, guard_on):
    class Boom(Exception):
        pass

    def boom():
        raise Boom

    fake = FakeContextVar()
    install(monkeypatch, fake)
    token = MutmutCallStack.set(("x", 1))
    fake.interrupt = boom

    with pytest.raises(Boom):
        MutmutCallStack.reset(token)

    # a later call on the same thread must work normally again
    assert MutmutCallStack.set(("z", 3)) == "token:('z', 3)"
    assert MutmutCallStack.get() == ("z", 3)


def test_guard_disabled_passes_everything_through(monkeypatch):
    monkeypatch.setattr(core, "_GUARD_REENTRANCY", False)
    seen = {}

    def finalizer():
        seen["set"] = MutmutCallStack.set(("nested", 9))

    fake = FakeContextVar(interrupt=finalizer)
    install(monkeypatch, fake)

    MutmutCallStack.set(("outer", 1))

    assert seen["set"] == "token:('nested', 9)"
    assert fake.calls == ["set", "set"]


def test_guard_is_per_thread(monkeypatch, guard_on):
    """One thread being inside set() must not turn another thread's calls into no-ops."""
    in_set = threading.Event()
    release = threading.Event()
    results = {}

    class BlockingVar(FakeContextVar):
        def set(self, value):
            if threading.current_thread().name == "slow":
                in_set.set()
                assert release.wait(timeout=10)
            return super().set(value)

    install(monkeypatch, BlockingVar())

    def slow():
        results["slow"] = MutmutCallStack.set(("slow", 1))

    t = threading.Thread(target=slow, name="slow")
    t.start()
    try:
        assert in_set.wait(timeout=10)
        results["other_set"] = MutmutCallStack.set(("other", 2))
        results["other_get"] = MutmutCallStack.get()
    finally:
        release.set()
        t.join(timeout=10)

    assert results["other_set"] == "token:('other', 2)"
    assert results["other_get"] == ("other", 2)
    assert results["slow"] == "token:('slow', 1)"


@pytest.mark.parametrize("enabled", [True, False])
def test_gc_state_is_never_modified(guard_on, enabled):
    """The fix must not touch process-wide GC state (disabling the GC would race across threads)."""
    thresholds = gc.get_threshold()
    was_enabled = gc.isenabled()
    (gc.enable if enabled else gc.disable)()
    try:
        token = MutmutCallStack.set(("a", 1))
        MutmutCallStack.get()
        MutmutCallStack.reset(token)
        assert gc.isenabled() is enabled
        assert gc.get_threshold() == thresholds
    finally:
        (gc.enable if was_enabled else gc.disable)()


REPRO_PYPROJECT = """
[project]
name = "repro596"
version = "0.0.0"
requires-python = ">=3.10"

[tool.mutmut]
source_paths = ["repro596"]
pytest_add_cli_args_test_selection = ["tests"]
"""

REPRO_DIRECT = """
class Node:
    def __del__(self):
        self.closed = 1 + 1  # mutable, so __del__ gets a trampoline


def make_garbage(n):
    a, b = Node(), Node()
    a.other, b.other = b, a  # reference cycle: freed only by the cyclic GC
    a.junk = [[] for _ in range(n)]  # vary allocations so the GC fires at varying points
    return 1 + 1
"""

REPRO_HELPER = """
def _close(node):
    node.closed = 1 + 1


class Node:
    def __del__(self):
        _close(self)  # the finalizer calls another trampolined function


def make_garbage(n):
    a, b = Node(), Node()
    a.other, b.other = b, a
    a.junk = [[] for _ in range(n)]
    return 1 + 1
"""

REPRO_TEST = """
from repro596.core import make_garbage


def test_make_garbage():
    for i in range(20_000):
        assert make_garbage(i % 13) == 2
"""


REPRO_TEST_THREADS = """
import threading

from repro596.core import make_garbage

errors = []


def _work():
    try:
        for i in range(5_000):
            assert make_garbage(i % 13) == 2
    except BaseException as e:  # exceptions in threads must fail the test, not just print a warning
        errors.append(e)


def test_make_garbage():
    threads = [threading.Thread(target=_work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
"""


@pytest.mark.skipif(sys.platform == "win32", reason="mutmut forks, which Windows does not support")
@pytest.mark.parametrize(
    ("core_source", "test_source"),
    [(REPRO_DIRECT, REPRO_TEST), (REPRO_HELPER, REPRO_TEST), (REPRO_DIRECT, REPRO_TEST_THREADS)],
    ids=["del-is-mutable", "del-calls-helper", "multithreaded"],
)
def test_stats_collection_survives_trampolined_finalizers(tmp_path: Path, core_source: str, test_source: str):
    """End-to-end regression for #596. Before the fix the two single-threaded cases segfault (exit -11) on CPython
    3.10 and 3.11. The multithreaded case did not fail on unfixed code in our runs; it is a concurrency
    non-regression check (finalizers on several threads, no hang, no crash)."""
    (tmp_path / "pyproject.toml").write_text(REPRO_PYPROJECT)
    (tmp_path / "repro596").mkdir()
    (tmp_path / "repro596" / "__init__.py").write_text("")
    (tmp_path / "repro596" / "core.py").write_text(textwrap.dedent(core_source))
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_core.py").write_text(textwrap.dedent(test_source))

    result = subprocess.run(
        [sys.executable, "-m", "mutmut", "run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, f"exit code {result.returncode}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
