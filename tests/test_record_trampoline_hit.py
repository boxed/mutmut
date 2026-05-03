import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

import mutmut
from mutmut.__main__ import record_trampoline_hit


class _FakeCode:
    def __init__(self, filename: str, name: str = "<func>") -> None:
        self.co_filename = filename
        self.co_name = name


class _FakeFrame:
    def __init__(self, code: _FakeCode, back: "_FakeFrame | None" = None) -> None:
        self.f_code = code
        self.f_back = back


def _make_chain(specs: list[tuple[str, str]]) -> _FakeFrame:
    """Build a frame chain from innermost to outermost.

    Each spec is ``(filename, function_name)``. The first entry is the deepest
    frame (the one ``inspect.currentframe()`` would return).
    """
    frame: _FakeFrame | None = None
    for fname, fn_name in reversed(specs):
        frame = _FakeFrame(_FakeCode(fname, fn_name), back=frame)
    assert frame is not None
    return frame


@pytest.fixture
def in_mutants_dir(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Create a fake ``./mutants`` directory and chdir into it.

    Uses ``tempfile.TemporaryDirectory`` rather than the ``tmp_path`` fixture so
    the resulting path does not contain the literal substring ``pytest`` (which
    the test-runner heuristic in ``record_trampoline_hit`` would treat as a
    test-runner frame and exit the walk early).

    A ``src/`` subdirectory is created so ``Config.get()`` can resolve
    ``source_paths`` via ``_guess_source_paths``.
    """
    with tempfile.TemporaryDirectory() as tmp:
        mutants = Path(tmp) / "mutants"
        (mutants / "src").mkdir(parents=True)
        monkeypatch.chdir(mutants)
        yield mutants


@pytest.fixture(autouse=True)
def clear_stats():
    mutmut._stats = set()
    yield
    mutmut._stats = set()


class TestMaxStackDepth:
    def test_records_hit_when_disabled(self, patch_config, in_mutants_dir: Path):
        patch_config("max_stack_depth", -1)
        record_trampoline_hit("foo.bar")
        assert "foo.bar" in mutmut._stats

    def test_records_within_budget(self, patch_config, in_mutants_dir: Path, monkeypatch: pytest.MonkeyPatch):
        user_file = str(in_mutants_dir / "user.py")
        chain = _make_chain(
            [
                (user_file, "_mutmut_trampoline"),
                (user_file, "user_inner"),
                (user_file, "user_outer"),
                ("/site-packages/pytest/runner.py", "pytest_runtest"),
            ]
        )
        monkeypatch.setattr("inspect.currentframe", lambda: chain)
        patch_config("max_stack_depth", 5)
        record_trampoline_hit("foo.bar")
        assert "foo.bar" in mutmut._stats

    def test_skips_when_over_budget(self, patch_config, in_mutants_dir: Path, monkeypatch: pytest.MonkeyPatch):
        user_file = str(in_mutants_dir / "user.py")
        chain = _make_chain(
            [
                (user_file, "_mutmut_trampoline"),
                (user_file, "user_a"),
                (user_file, "user_b"),
                (user_file, "user_c"),
                ("/site-packages/pytest/runner.py", "pytest_runtest"),
            ]
        )
        monkeypatch.setattr("inspect.currentframe", lambda: chain)
        patch_config("max_stack_depth", 2)
        record_trampoline_hit("foo.bar")
        assert "foo.bar" not in mutmut._stats

    def test_third_party_frames_do_not_count(self, patch_config, in_mutants_dir: Path, monkeypatch: pytest.MonkeyPatch):
        user_file = str(in_mutants_dir / "user.py")
        chain = _make_chain(
            [
                (user_file, "_mutmut_trampoline"),
                (user_file, "user_inner"),
                ("/site-packages/django/middleware.py", "process_request"),
                ("/site-packages/django/handlers.py", "get_response"),
                ("/site-packages/requests/sessions.py", "send"),
                (user_file, "user_outer"),
                ("/site-packages/pytest/runner.py", "pytest_runtest"),
            ]
        )
        monkeypatch.setattr("inspect.currentframe", lambda: chain)
        # Two user frames, three 3rd-party frames between them. Budget of 2
        # exactly covers the user frames; 3rd-party frames must not consume it.
        patch_config("max_stack_depth", 3)
        record_trampoline_hit("foo.bar")
        assert "foo.bar" in mutmut._stats

    def test_mutmut_trampoline_frame_does_not_count(
        self, patch_config, in_mutants_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        user_file = str(in_mutants_dir / "user.py")
        # Many _mutmut_trampoline frames must not eat the budget even though
        # they live inside the mutants directory. With one user frame and a
        # budget of 2, the call must be recorded; if the trampoline frames
        # were counted the budget would be exhausted.
        chain = _make_chain(
            [
                (user_file, "_mutmut_trampoline"),
                (user_file, "_mutmut_trampoline"),
                (user_file, "_mutmut_trampoline"),
                (user_file, "user_only_frame"),
                ("/site-packages/pytest/runner.py", "pytest_runtest"),
            ]
        )
        monkeypatch.setattr("inspect.currentframe", lambda: chain)
        patch_config("max_stack_depth", 2)
        record_trampoline_hit("foo.bar")
        assert "foo.bar" in mutmut._stats

    def test_filename_with_pytest_substring_breaks_walk(
        self, patch_config, in_mutants_dir: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Preserve existing behavior: any frame whose filename contains
        # ``pytest`` / ``hammett`` / ``unittest`` ends the walk.
        user_file = str(in_mutants_dir / "user.py")
        chain = _make_chain(
            [
                (user_file, "_mutmut_trampoline"),
                ("/site-packages/hammett/main.py", "run"),
                (user_file, "ignored_after_break"),
            ]
        )
        monkeypatch.setattr("inspect.currentframe", lambda: chain)
        patch_config("max_stack_depth", 1)
        record_trampoline_hit("foo.bar")
        # Walk breaks at hammett frame before ever decrementing; budget intact.
        assert "foo.bar" in mutmut._stats
