"""Tests for fork_isolation utilities."""

import os
from datetime import datetime
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from mutmut.models.mutant_status import MutantStatus
from mutmut.workers.isolation import ForkRunner
from mutmut.workers.isolation import HotForkRunner
from mutmut.workers.isolation import MutantResult
from mutmut.workers.isolation import OrchestratorCrashError
from mutmut.workers.isolation import RunningWorker
from mutmut.workers.isolation import run_in_fork
from mutmut.workers.isolation import run_in_fork_with_result


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestRunInForkWithResult:
    """Tests for run_in_fork_with_result."""

    def test_returns_simple_value(self):
        """Function return value is passed back to parent."""
        result = run_in_fork_with_result(lambda: 42)
        assert result == 42

    def test_returns_complex_value(self):
        """Complex picklable objects are returned correctly."""
        result = run_in_fork_with_result(lambda: {"a": [1, 2, 3], "b": "hello"})
        assert result == {"a": [1, 2, 3], "b": "hello"}

    def test_passes_args_and_kwargs(self):
        """Arguments are passed to the function."""

        def add(a, b, multiplier=1):
            return (a + b) * multiplier

        result = run_in_fork_with_result(add, 2, 3, multiplier=10)
        assert result == 50

    def test_child_import_does_not_affect_parent(self):
        """Imports in child don't pollute parent's namespace."""

        def import_and_use():
            import json

            return json.dumps({"test": True})

        result = run_in_fork_with_result(import_and_use)
        assert result == '{"test": true}'

    def test_child_crash_raises_error(self):
        """Child process crash raises ChildProcessError."""

        def crash():
            raise RuntimeError("boom")

        with pytest.raises(ChildProcessError):
            run_in_fork_with_result(crash)

    def test_child_crash_includes_error_message(self):
        """ChildProcessError includes the original exception message."""

        def crash():
            raise RuntimeError("specific error message")

        with pytest.raises(ChildProcessError) as exc_info:
            run_in_fork_with_result(crash)

        assert "specific error message" in str(exc_info.value)

    def test_no_temp_files_created(self, tmp_path, monkeypatch):
        """Pipe-based transport doesn't create temp files."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        run_in_fork_with_result(lambda: "test")

        # No pickle files should exist
        assert not list(tmp_path.glob("**/*.pickle"))


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestRunInFork:
    """Tests for run_in_fork (returns exit code)."""

    def test_returns_zero_on_success(self):
        """Returns 0 when function returns 0."""
        result = run_in_fork(lambda: 0)
        assert result == 0

    def test_returns_function_exit_code(self):
        """Returns the exit code from the function."""
        result = run_in_fork(lambda: 42)
        assert result == 42

    def test_returns_one_on_exception(self):
        """Returns 1 when function raises."""

        def crash():
            raise RuntimeError("boom")

        result = run_in_fork(crash)
        assert result == 1

    def test_side_effects_in_child(self, tmp_path):
        """Side effects happen in child (verifiable via file)."""
        marker = tmp_path / "marker.txt"

        def create_marker():
            marker.write_text("created")
            return 0

        run_in_fork(create_marker)

        assert marker.read_text() == "created"


class TestOrchestratorCrashError:
    """Tests for OrchestratorCrashError exception."""

    def test_error_message_includes_exit_code(self):
        """Exit code is included in message."""
        err = OrchestratorCrashError(exit_code=1, lost_mutants=[])
        assert "exit code: 1" in str(err)

    def test_error_message_lists_lost_mutants(self):
        """Lost mutants are listed in message."""
        err = OrchestratorCrashError(exit_code=1, lost_mutants=["mutant_1", "mutant_2"])
        assert "mutant_1" in str(err)
        assert "mutant_2" in str(err)
        assert "2 in-flight mutant(s)" in str(err)

    def test_truncates_long_mutant_list(self):
        """Only first 10 mutants shown, rest summarized."""
        mutants = [f"mutant_{i}" for i in range(15)]
        err = OrchestratorCrashError(exit_code=1, lost_mutants=mutants)

        assert "mutant_0" in str(err)
        assert "mutant_9" in str(err)
        assert "mutant_10" not in str(err)
        assert "5 more" in str(err)

    def test_includes_resume_instructions(self):
        """Message includes how to resume."""
        err = OrchestratorCrashError(exit_code=1, lost_mutants=[])
        assert "mutmut run" in str(err)

    def test_includes_crash_log_path(self):
        """Crash log path is shown if provided."""
        err = OrchestratorCrashError(exit_code=1, lost_mutants=[], crash_log="mutants/.orchestrator-crash.log")
        assert ".orchestrator-crash.log" in str(err)

    def test_attributes_accessible(self):
        """Exception attributes are accessible."""
        err = OrchestratorCrashError(exit_code=42, lost_mutants=["a", "b"], crash_log="/path/to/log")
        assert err.exit_code == 42
        assert err.lost_mutants == ["a", "b"]
        assert err.crash_log == "/path/to/log"

    def test_empty_lost_mutants(self):
        """Works correctly with empty lost mutants list."""
        err = OrchestratorCrashError(exit_code=0, lost_mutants=[])
        assert "0 in-flight mutant(s)" in str(err)

    def test_no_crash_log(self):
        """Works correctly without crash log."""
        err = OrchestratorCrashError(exit_code=1, lost_mutants=["m1"])
        # Should not raise and should not include "Crash log:"
        msg = str(err)
        assert "Crash log:" not in msg

    def test_is_exception(self):
        """OrchestratorCrashError is an Exception subclass."""
        err = OrchestratorCrashError(exit_code=1, lost_mutants=[])
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        """Exception can be raised and caught properly."""
        with pytest.raises(OrchestratorCrashError) as exc_info:
            raise OrchestratorCrashError(exit_code=255, lost_mutants=["test_mutant"], crash_log="/tmp/crash.log")

        assert exc_info.value.exit_code == 255
        assert exc_info.value.lost_mutants == ["test_mutant"]
        assert exc_info.value.crash_log == "/tmp/crash.log"


class TestMutantResult:
    """Tests for MutantResult dataclass."""

    def test_basic_creation(self):
        """MutantResult can be created with basic fields."""
        result = MutantResult(
            mutant_name="test__mutmut_1",
            exit_code=0,
            status=MutantStatus.SURVIVED,
            duration=1.5,
        )
        assert result.mutant_name == "test__mutmut_1"
        assert result.exit_code == 0
        assert result.status == MutantStatus.SURVIVED
        assert result.duration == 1.5
        assert result.output is None

    def test_with_output(self):
        """MutantResult can include output."""
        result = MutantResult(
            mutant_name="test__mutmut_1",
            exit_code=1,
            status=MutantStatus.KILLED,
            duration=0.5,
            output="Test failed: assertion error",
        )
        assert result.output == "Test failed: assertion error"


class TestHotForkRunner:
    """Tests for HotForkRunner."""

    @pytest.fixture
    def mock_test_runner_class(self):
        """Create a mock test runner class."""

        class MockRunner:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def run_tests(self, mutant_name, tests):
                # Return 0 for killed, 1 for survived
                if "survive" in mutant_name:
                    return 1
                return 0

            def warm_up(self):
                pass

        return MockRunner

    def test_init_sets_attributes(self, mock_test_runner_class):
        """__init__ sets all expected attributes."""
        runner = HotForkRunner(
            max_workers=4,
            test_runner_class=mock_test_runner_class,
            test_runner_args={"foo": "bar"},
            debug=True,
            max_restarts=5,
        )

        assert runner.max_workers == 4
        assert runner.test_runner_class == mock_test_runner_class
        assert runner.test_runner_args == {"foo": "bar"}
        assert runner.debug is True
        assert runner.max_restarts == 5

    def test_init_defaults(self, mock_test_runner_class):
        """__init__ has sensible defaults."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        assert runner.debug is False
        assert runner.max_restarts == HotForkRunner.DEFAULT_MAX_RESTARTS
        assert runner._pending == set()
        assert runner._pending_work == {}
        assert runner._shutting_down is False
        assert runner._restart_count == 0

    def test_has_capacity_respects_max_workers(self, mock_test_runner_class):
        """has_capacity() is False when at max pending."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        runner._pending = set()
        assert runner.has_capacity() is True

        runner._pending = {"m1"}
        assert runner.has_capacity() is True

        runner._pending = {"m1", "m2"}
        assert runner.has_capacity() is False

        runner._pending = {"m1", "m2", "m3"}
        assert runner.has_capacity() is False

    def test_pending_count(self, mock_test_runner_class):
        """pending_count() returns number of in-flight mutants."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        runner._pending = set()
        assert runner.pending_count() == 0

        runner._pending = {"a", "b", "c"}
        assert runner.pending_count() == 3

    def test_get_orchestrator_restart_count(self, mock_test_runner_class):
        """get_orchestrator_restart_count() returns restart counter."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        assert runner.get_orchestrator_restart_count() == 0

        runner._restart_count = 3
        assert runner.get_orchestrator_restart_count() == 3

    def test_get_active_workers_empty_when_no_orchestrator(self, mock_test_runner_class):
        """get_active_workers() returns empty list when no orchestrator."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        assert runner.get_active_workers() == []

    @pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
    def test_startup_creates_orchestrator(self, mock_test_runner_class):
        """startup() forks an orchestrator process."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        with patch("os.fork") as mock_fork:
            mock_fork.return_value = 12345  # Parent sees child PID
            with patch("os.pipe") as mock_pipe:
                mock_pipe.side_effect = [(3, 4), (5, 6)]
                with patch("os.close"):
                    runner.startup()

        assert runner.orchestrator_pid == 12345

    def test_signal_work_complete_closes_pipe(self, mock_test_runner_class):
        """signal_work_complete() closes the work pipe."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )

        # Simulate that startup has been called
        runner.work_pipe_write = 999

        with patch("os.close") as mock_close:
            runner.signal_work_complete()
            mock_close.assert_called_once_with(999)

        assert runner.work_pipe_write is None

    def test_signal_work_complete_noop_when_already_closed(self, mock_test_runner_class):
        """signal_work_complete() is a no-op when pipe already closed."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
        )
        runner.work_pipe_write = None

        with patch("os.close") as mock_close:
            runner.signal_work_complete()  # Should not raise
            mock_close.assert_not_called()

    def test_orchestrator_crash_detection(self, mock_test_runner_class):
        """Orchestrator crash raises OrchestratorCrashError after max restarts."""
        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=mock_test_runner_class,
            test_runner_args={},
            max_restarts=0,  # No restarts allowed
        )
        runner.orchestrator_pid = 99999
        runner._pending = {"lost_mutant"}

        with patch("os.waitpid") as mock_wait:
            # Simulate orchestrator exited with code 1
            mock_wait.return_value = (99999, 256)  # exit code 1

            with pytest.raises(OrchestratorCrashError) as exc_info:
                runner._check_orchestrator_alive()

            assert "lost_mutant" in exc_info.value.lost_mutants


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestHotForkRunnerIntegration:
    """Integration tests for HotForkRunner (actually forks)."""

    def test_full_lifecycle(self, tmp_path, monkeypatch):
        """Full startup -> submit -> wait -> shutdown cycle."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()
        # Create src directory so config() doesn't fail when guessing paths_to_mutate
        (tmp_path / "src").mkdir()

        # Reset the config singleton so it re-loads from the new directory
        import mutmut.configuration

        monkeypatch.setattr(mutmut.configuration, "_config", None)

        class SimpleRunner:
            def __init__(self):
                pass

            def run_tests(self, mutant_name, tests):
                # Return 1 for killed (test fails), 0 for survived (test passes)
                return 1 if "kill" in mutant_name else 0

            def warm_up(self):
                pass

        runner = HotForkRunner(
            max_workers=2,
            test_runner_class=SimpleRunner,
            test_runner_args={},
        )

        runner.startup()

        try:
            runner.submit("mutant_kill_1", ["test"], cpu_time_limit=30, estimated_time=1.0)

            # Signal work complete before waiting for results
            runner.signal_work_complete()

            result = runner.wait_for_result(timeout=10.0)

            assert result.mutant_name == "mutant_kill_1"
            assert result.exit_code == 1  # killed (test failed)
            assert result.status == MutantStatus.KILLED
        finally:
            runner.shutdown()


class TestRunningWorker:
    """Tests for RunningWorker NamedTuple."""

    def test_basic_creation(self):
        """RunningWorker can be created with required fields."""
        now = datetime.now()
        worker = RunningWorker(mutant_name="test__mutmut_1", start_time=now, estimated_time=2.5)

        assert worker.mutant_name == "test__mutmut_1"
        assert worker.start_time == now
        assert worker.estimated_time == 2.5

    def test_is_namedtuple(self):
        """RunningWorker is a NamedTuple with accessible fields."""
        now = datetime.now()
        worker = RunningWorker("m1", now, 1.0)

        # Access by index
        assert worker[0] == "m1"
        assert worker[1] == now
        assert worker[2] == 1.0

        # Access by name
        assert worker.mutant_name == "m1"


class TestForkRunner:
    """Tests for ForkRunner."""

    def test_init_sets_attributes(self):
        """__init__ sets all expected attributes."""
        mock_runner = Mock()
        runner = ForkRunner(
            max_workers=4,
            test_runner=mock_runner,
            debug=True,
        )

        assert runner.max_workers == 4
        assert runner.test_runner == mock_runner
        assert runner.debug is True
        assert runner._running == {}

    def test_init_defaults(self):
        """__init__ has sensible defaults."""
        mock_runner = Mock()
        runner = ForkRunner(max_workers=2, test_runner=mock_runner)

        assert runner.debug is False
        assert runner._running == {}

    def test_has_capacity_empty(self):
        """has_capacity() is True when no workers running."""
        runner = ForkRunner(max_workers=2, test_runner=Mock(), debug=False)
        assert runner.has_capacity() is True

    def test_has_capacity_below_limit(self):
        """has_capacity() is True when below max_workers."""
        runner = ForkRunner(max_workers=4, test_runner=Mock(), debug=False)
        runner._running = {
            1: RunningWorker("m1", datetime.now(), 1.0),
            2: RunningWorker("m2", datetime.now(), 1.0),
        }
        assert runner.has_capacity() is True

    def test_has_capacity_at_limit(self):
        """has_capacity() is False when at max_workers."""
        runner = ForkRunner(max_workers=2, test_runner=Mock(), debug=False)
        runner._running = {
            1: RunningWorker("m1", datetime.now(), 1.0),
            2: RunningWorker("m2", datetime.now(), 1.0),
        }
        assert runner.has_capacity() is False

    def test_has_capacity_over_limit(self):
        """has_capacity() is False when over max_workers."""
        runner = ForkRunner(max_workers=2, test_runner=Mock(), debug=False)
        runner._running = {
            1: RunningWorker("m1", datetime.now(), 1.0),
            2: RunningWorker("m2", datetime.now(), 1.0),
            3: RunningWorker("m3", datetime.now(), 1.0),
        }
        assert runner.has_capacity() is False

    def test_pending_count_empty(self):
        """pending_count() returns 0 when no workers running."""
        runner = ForkRunner(max_workers=4, test_runner=Mock(), debug=False)
        assert runner.pending_count() == 0

    def test_pending_count_with_workers(self):
        """pending_count() returns number of running workers."""
        runner = ForkRunner(max_workers=4, test_runner=Mock(), debug=False)
        runner._running = {
            1: RunningWorker("m1", datetime.now(), 1.0),
            2: RunningWorker("m2", datetime.now(), 1.0),
            3: RunningWorker("m3", datetime.now(), 1.0),
        }
        assert runner.pending_count() == 3

    def test_get_active_workers_empty(self):
        """get_active_workers() returns empty list when no workers."""
        runner = ForkRunner(max_workers=4, test_runner=Mock(), debug=False)
        assert runner.get_active_workers() == []

    def test_get_active_workers_format(self):
        """get_active_workers() returns list of ActiveWorker with correct data."""
        runner = ForkRunner(max_workers=4, test_runner=Mock(), debug=False)
        now = datetime.now()
        runner._running = {
            123: RunningWorker("mutant_1", now, 2.5),
            456: RunningWorker("mutant_2", now, 3.0),
        }

        workers = runner.get_active_workers()

        assert len(workers) == 2
        # Find the worker with pid 123
        worker_123 = next(w for w in workers if w.pid == 123)
        assert worker_123.mutant_name == "mutant_1"
        assert worker_123.estimated_time == 2.5
        assert worker_123.start_time == now

    def test_get_orchestrator_restart_count_always_zero(self):
        """ForkRunner has no orchestrator, always returns 0."""
        runner = ForkRunner(max_workers=2, test_runner=Mock(), debug=False)
        assert runner.get_orchestrator_restart_count() == 0

    def test_startup_freezes_gc(self):
        """startup() freezes gc for ForkRunner."""
        runner = ForkRunner(max_workers=2, test_runner=Mock(), debug=False)
        runner.startup()  # Should not raise
        assert runner._running == {}
        # Clean up: unfreeze gc
        import gc

        gc.unfreeze()

    def test_signal_work_complete_is_noop(self):
        """signal_work_complete() is a no-op for ForkRunner."""
        runner = ForkRunner(max_workers=2, test_runner=Mock(), debug=False)
        runner.signal_work_complete()  # Should not raise


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestForkRunnerIntegration:
    """Integration tests for ForkRunner (actually forks).

    Uses the real state() singleton (survives fork) and patches out C extensions
    (setproctitle) and thread-spawning helpers (register_timeout) that are
    unsafe or unnecessary in the test environment.
    """

    @pytest.fixture(autouse=True)
    def _setup_fork_env(self):
        """Set up real state and patch fork-unsafe helpers."""
        from mutmut.state import reset_state
        from mutmut.state import state

        reset_state()
        state().duration_by_test = {"test_one": 0.1, "test": 0.1}
        with (
            patch("mutmut.workers.isolation.setproctitle", lambda *a, **kw: None),
            patch("mutmut.workers.isolation.register_timeout", lambda *a, **kw: None),
        ):
            yield
        reset_state()

    def test_submit_and_wait_killed(self, tmp_path, monkeypatch):
        """Submit a mutant that gets killed (test fails)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        class SimpleRunner:
            def run_tests(self, mutant_name, tests):
                return 1  # Test fails = mutant killed

        runner = ForkRunner(max_workers=2, test_runner=SimpleRunner(), debug=False)

        runner.submit("mutant_1", ["test_one"], cpu_time_limit=30, estimated_time=1.0)

        result = runner.wait_for_result()

        assert result.mutant_name == "mutant_1"
        assert result.exit_code == 1
        assert result.status == MutantStatus.KILLED
        assert result.duration > 0

    def test_submit_and_wait_survived(self, tmp_path, monkeypatch):
        """Submit a mutant that survives (test passes)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        class SimpleRunner:
            def run_tests(self, mutant_name, tests):
                return 0  # Test passes = mutant survived

        runner = ForkRunner(max_workers=2, test_runner=SimpleRunner(), debug=False)

        runner.submit("mutant_1", ["test_one"], cpu_time_limit=30, estimated_time=1.0)

        result = runner.wait_for_result()

        assert result.mutant_name == "mutant_1"
        assert result.exit_code == 0
        assert result.status == MutantStatus.SURVIVED

    def test_no_tests_exit_code(self, tmp_path, monkeypatch):
        """Empty tests list results in exit code 33 (NO_TESTS)."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        class SimpleRunner:
            def run_tests(self, mutant_name, tests):
                return 0

        runner = ForkRunner(max_workers=2, test_runner=SimpleRunner(), debug=False)

        runner.submit("mutant_1", [], cpu_time_limit=30, estimated_time=1.0)

        result = runner.wait_for_result()

        assert result.exit_code == 33
        assert result.status == MutantStatus.NO_TESTS

    def test_shutdown_waits_for_children(self, tmp_path, monkeypatch):
        """shutdown() waits for all running children to complete."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        class SimpleRunner:
            def run_tests(self, mutant_name, tests):
                return 1

        runner = ForkRunner(max_workers=4, test_runner=SimpleRunner(), debug=False)

        runner.submit("mutant_1", ["test"], cpu_time_limit=30, estimated_time=1.0)
        runner.submit("mutant_2", ["test"], cpu_time_limit=30, estimated_time=1.0)

        assert runner.pending_count() == 2

        runner.shutdown()

        assert runner.pending_count() == 0
