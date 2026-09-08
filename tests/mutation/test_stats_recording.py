"""Recording which functions a test reaches (stats collection) must be cheap and robust."""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest

import mutmut.__main__
import mutmut.mutation.trampoline as trampoline_module
from mutmut.__main__ import FRAME_MUTATED_SOURCE
from mutmut.__main__ import FRAME_OTHER
from mutmut.__main__ import FRAME_TEST_FRAMEWORK
from mutmut.__main__ import _frame_classification_cache
from mutmut.__main__ import classify_frame_filename
from mutmut.__main__ import record_trampoline_hit
from mutmut.configuration import Config
from mutmut.mutation.trampoline import _get_dependency_depth
from mutmut.mutation.trampoline import _needs_recording
from mutmut.mutation.trampoline import set_dependency_depth
from mutmut.mutation.trampoline import set_mutant_under_test
from mutmut.mutation.trampoline import wrap_in_trampoline
from mutmut.state import reset_state
from mutmut.state import state


def _config(monkeypatch, project_dir: Path, *, max_stack_depth: int = -1, track_dependencies: bool = True) -> Mock:
    cfg = Mock(spec=Config)
    cfg.max_stack_depth = max_stack_depth
    cfg.source_paths = [Path("src")]
    cfg.resolved_mutated_source_paths = [project_dir / "mutants" / "src"]
    cfg.track_dependencies = track_dependencies
    monkeypatch.setattr(mutmut.__main__, "config", lambda: cfg)
    monkeypatch.setattr(trampoline_module, "config", lambda: cfg)
    return cfg


@pytest.fixture
def project_dir() -> Iterator[Path]:
    """A scratch directory whose path does not contain "pytest".

    Frames from files whose path contains "pytest" (or "unittest") are treated as test
    framework frames, and pytest's own tmp_path lives under /tmp/pytest-of-<user>/."""
    with tempfile.TemporaryDirectory(prefix="mutmut-stats-") as directory:
        yield Path(directory)


@pytest.fixture(autouse=True)
def _fresh_state() -> Iterator[None]:
    reset_state()
    _frame_classification_cache.clear()
    set_dependency_depth(None)
    yield
    reset_state()
    _frame_classification_cache.clear()
    set_dependency_depth(None)
    set_mutant_under_test("")


class TestClassifyFrameFilename:
    def test_mutated_source_test_framework_and_other_files(self, monkeypatch, project_dir):
        _config(monkeypatch, project_dir)
        mutated = project_dir / "mutants" / "src" / "pkg" / "mod.py"
        mutated.parent.mkdir(parents=True)
        mutated.touch()
        elsewhere = project_dir / "lib" / "other.py"
        elsewhere.parent.mkdir()
        elsewhere.touch()

        assert classify_frame_filename(str(mutated)) == FRAME_MUTATED_SOURCE
        assert classify_frame_filename(str(elsewhere)) == FRAME_OTHER
        assert classify_frame_filename("/site-packages/_pytest/python.py") == FRAME_TEST_FRAMEWORK
        assert classify_frame_filename("/site-packages/unittest/case.py") == FRAME_TEST_FRAMEWORK

    def test_frames_without_a_file_do_not_raise(self, monkeypatch, project_dir):
        _config(monkeypatch, project_dir)

        assert classify_frame_filename("<string>") == FRAME_OTHER
        assert classify_frame_filename("<frozen importlib._bootstrap>") == FRAME_OTHER
        assert classify_frame_filename(str(project_dir / "deleted.py")) == FRAME_OTHER

    def test_absolute_filenames_are_cached_relative_ones_are_not(self, monkeypatch, project_dir):
        cfg = _config(monkeypatch, project_dir)
        absolute = str(project_dir / "mutants" / "src" / "mod.py")
        classify_frame_filename(absolute)
        classify_frame_filename("src/mod.py")

        assert absolute in _frame_classification_cache
        assert "src/mod.py" not in _frame_classification_cache

        # the cache answers without looking at the configuration again
        cfg.resolved_mutated_source_paths = []
        assert classify_frame_filename(absolute) == FRAME_MUTATED_SOURCE


class TestRecordTrampolineHit:
    def test_records_from_code_without_a_file(self, monkeypatch, project_dir):
        """Frames whose co_filename is not a file (compiled from a string) used to raise."""
        _config(monkeypatch, project_dir, max_stack_depth=3)
        namespace: dict[str, object] = {"record_trampoline_hit": record_trampoline_hit}
        exec(compile("def hit():\n    record_trampoline_hit('mod.x_foo')\n", "<string>", "exec"), namespace)

        namespace["hit"]()  # type: ignore[operator]

        assert "mod.x_foo" in state()._stats

    def test_counts_only_frames_from_mutated_sources_towards_the_depth(self, monkeypatch, project_dir):
        _config(monkeypatch, project_dir, max_stack_depth=2)
        module_path = project_dir / "mutants" / "src" / "deep.py"
        module_path.parent.mkdir(parents=True)
        module_path.write_text(
            "def level3():\n"
            "    record_trampoline_hit('deep.x_level3')\n"
            "def level2():\n"
            "    level3()\n"
            "def level1():\n"
            "    level2()\n"
        )
        namespace: dict[str, object] = {"record_trampoline_hit": record_trampoline_hit}
        exec(compile(module_path.read_text(), str(module_path), "exec"), namespace)

        namespace["level1"]()  # type: ignore[operator]

        # three frames of mutated source lie between the hit and this test: deeper than allowed
        assert "deep.x_level3" not in state()._stats

        namespace["level3"]()  # type: ignore[operator]
        assert "deep.x_level3" in state()._stats


class TestNeedsRecording:
    def test_first_hit_is_always_recorded(self, monkeypatch, project_dir):
        _config(monkeypatch, project_dir)
        assert _needs_recording("mod.x_foo", None)
        assert _needs_recording("mod.x_foo", "mod.x_caller")

    def test_known_hit_and_known_caller_are_skipped(self, monkeypatch, project_dir):
        _config(monkeypatch, project_dir)
        state()._stats.add("mod.x_foo")
        state().function_dependencies["mod.x_foo"].add("mod.x_caller")

        assert not _needs_recording("mod.x_foo", None)
        assert not _needs_recording("mod.x_foo", "mod.x_caller")
        assert _needs_recording("mod.x_foo", "mod.x_other_caller")

    def test_callers_are_irrelevant_when_dependency_tracking_is_off(self, monkeypatch, project_dir):
        _config(monkeypatch, project_dir, track_dependencies=False)
        state()._stats.add("mod.x_foo")

        assert not _needs_recording("mod.x_foo", "mod.x_caller")


class TestDependencyDepth:
    def test_explicit_value_wins_over_the_environment(self, monkeypatch):
        monkeypatch.setenv("MUTMUT_DEPENDENCY_DEPTH", "5")
        set_dependency_depth(2)
        assert _get_dependency_depth() == 2

    def test_environment_is_read_once(self, monkeypatch):
        monkeypatch.setenv("MUTMUT_DEPENDENCY_DEPTH", "5")
        assert _get_dependency_depth() == 5
        monkeypatch.delenv("MUTMUT_DEPENDENCY_DEPTH")
        assert _get_dependency_depth() == 5

    def test_defaults_to_unlimited(self, monkeypatch):
        monkeypatch.delenv("MUTMUT_DEPENDENCY_DEPTH", raising=False)
        assert _get_dependency_depth() == -1


mutants_counted = {}


@wrap_in_trampoline(mutants_counted)
def counted(a: int) -> int:
    return a


def x_counted__mutmut_orig(a: int) -> int:
    return a


mutants_counted["_mutmut_orig"] = x_counted__mutmut_orig


def test_trampoline_records_a_function_once_per_test(monkeypatch, project_dir):
    _config(monkeypatch, project_dir)
    recorded: list[tuple[str, str | None]] = []

    def fake_record(name: str, caller: str | None = None) -> None:
        recorded.append((name, caller))
        state()._stats.add(name)

    monkeypatch.setattr(trampoline_module, "record_trampoline_hit", fake_record)
    set_mutant_under_test("stats")

    for i in range(100):
        assert counted(i) == i

    assert recorded == [(f"{__name__}.x_counted", None)]
    assert os.environ["MUTANT_UNDER_TEST"] == "stats"
