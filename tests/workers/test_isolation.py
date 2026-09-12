"""Tests for fork isolation utilities."""

import os
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

from mutmut.configuration import ProcessIsolation
from mutmut.configuration import config
from mutmut.configuration import reset_config
from mutmut.runners.harness import ListAllTestsResult
from mutmut.state import reset_state
from mutmut.state import state
from mutmut.workers.isolation import ForkRunner
from mutmut.workers.isolation import ForkServerCrashError
from mutmut.workers.isolation import ForkServerRunner
from mutmut.workers.isolation import get_mutant_runner
from mutmut.workers.isolation import recv_message
from mutmut.workers.isolation import run_in_fork
from mutmut.workers.isolation import run_in_fork_with_result
from mutmut.workers.isolation import send_message


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

    def test_child_crash_includes_child_traceback(self):
        """Without this the parent only reports where it forked, not what failed."""

        def crash():
            def inner_frame_with_a_distinctive_name():
                raise RuntimeError("boom")

            inner_frame_with_a_distinctive_name()

        with pytest.raises(ChildProcessError) as exc_info:
            run_in_fork_with_result(crash)

        message = str(exc_info.value)
        assert "Traceback from the child process:" in message
        assert "inner_frame_with_a_distinctive_name" in message

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


class TestForkServerCrashError:
    """Tests for ForkServerCrashError exception."""

    def test_error_message_includes_exit_code(self):
        """Exit code is included in message."""
        err = ForkServerCrashError(exit_code=1, lost_mutants=[])
        assert "exit code: 1" in str(err)

    def test_error_message_lists_lost_mutants(self):
        """Lost mutants are listed in message."""
        err = ForkServerCrashError(exit_code=1, lost_mutants=["mutant_1", "mutant_2"])
        assert "mutant_1" in str(err)
        assert "mutant_2" in str(err)
        assert "2 in-flight mutant(s)" in str(err)

    def test_truncates_long_mutant_list(self):
        """Only first 10 mutants shown, rest summarized."""
        mutants = [f"mutant_{i}" for i in range(15)]
        err = ForkServerCrashError(exit_code=1, lost_mutants=mutants)

        assert "mutant_0" in str(err)
        assert "mutant_9" in str(err)
        assert "mutant_10" not in str(err)
        assert "5 more" in str(err)

    def test_includes_resume_instructions(self):
        """Message includes how to resume."""
        err = ForkServerCrashError(exit_code=1, lost_mutants=[])
        assert "mutmut run" in str(err)

    def test_includes_crash_log_path(self):
        """Crash log path is shown if provided."""
        err = ForkServerCrashError(exit_code=1, lost_mutants=[], crash_log="mutants/.forkserver-crash.log")
        assert ".forkserver-crash.log" in str(err)

    def test_attributes_accessible(self):
        """Exception attributes are accessible."""
        err = ForkServerCrashError(exit_code=42, lost_mutants=["a", "b"], crash_log="/path/to/log")
        assert err.exit_code == 42
        assert err.lost_mutants == ["a", "b"]
        assert err.crash_log == "/path/to/log"

    def test_empty_lost_mutants(self):
        """Works correctly with empty lost mutants list."""
        err = ForkServerCrashError(exit_code=0, lost_mutants=[])
        assert "0 in-flight mutant(s)" in str(err)

    def test_no_crash_log(self):
        """Works correctly without crash log."""
        err = ForkServerCrashError(exit_code=1, lost_mutants=["m1"])
        # Should not raise and should not include "Crash log:"
        msg = str(err)
        assert "Crash log:" not in msg

    def test_is_exception(self):
        """ForkServerCrashError is an Exception subclass."""
        err = ForkServerCrashError(exit_code=1, lost_mutants=[])
        assert isinstance(err, Exception)

    def test_can_be_raised_and_caught(self):
        """Exception can be raised and caught properly."""
        with pytest.raises(ForkServerCrashError) as exc_info:
            raise ForkServerCrashError(exit_code=255, lost_mutants=["test_mutant"], crash_log="/tmp/crash.log")

        assert exc_info.value.exit_code == 255
        assert exc_info.value.lost_mutants == ["test_mutant"]
        assert exc_info.value.crash_log == "/tmp/crash.log"


class TestForkRunnerNoTestMutants:
    """A mutant with no tests is resolved without forking, but it is still a result
    the caller has to be able to collect. See the drain loop in MutantRunner's docstring."""

    @staticmethod
    def _runner(max_workers=4):
        # test_runner is never touched on the no-tests path.
        return ForkRunner(max_workers=max_workers, test_runner=object(), debug=False)

    @staticmethod
    def _submit_without_tests(runner, mutant_name="mod.x_foo__mutmut_1"):
        runner.submit(mutant_name, [], cpu_time_limit=1, estimated_time=0.0)

    def test_submitting_without_tests_does_not_fork(self, monkeypatch):
        """No tests means no work, so no child process should be spawned."""

        def explode():
            raise AssertionError("os.fork() must not be called for a mutant with no tests")

        monkeypatch.setattr(os, "fork", explode)
        self._submit_without_tests(self._runner())

    def test_queued_result_counts_as_pending(self):
        """pending_count() drives the caller's drain loop, so it has to see queued results."""
        runner = self._runner()
        self._submit_without_tests(runner)
        assert runner.pending_count() == 1

    def test_queued_result_does_not_consume_a_worker_slot(self):
        """Nothing is running, so capacity is unaffected however many are queued."""
        runner = self._runner(max_workers=1)
        self._submit_without_tests(runner, "mod.x_foo__mutmut_1")
        self._submit_without_tests(runner, "mod.x_foo__mutmut_2")
        assert runner.has_capacity()

    def test_documented_drain_loop_collects_the_result(self):
        """The submit/pending_count/wait_for_result loop must not drop the mutant."""
        runner = self._runner()
        self._submit_without_tests(runner)

        runner.signal_work_complete()
        drained = []
        while runner.pending_count() > 0:
            drained.append(runner.wait_for_result())

        assert [(r.mutant_name, r.exit_code) for r in drained] == [("mod.x_foo__mutmut_1", 33)]

    def test_queued_results_are_drained_in_submission_order(self):
        """Results are reported against mutant names, so order must stay stable."""
        runner = self._runner()
        for i in (1, 2, 3):
            self._submit_without_tests(runner, f"mod.x_foo__mutmut_{i}")

        drained = [runner.wait_for_result().mutant_name for _ in range(runner.pending_count())]

        assert drained == ["mod.x_foo__mutmut_1", "mod.x_foo__mutmut_2", "mod.x_foo__mutmut_3"]
        assert runner.pending_count() == 0


class TestGetMutantRunner:
    """Tests for the get_mutant_runner factory."""

    @pytest.fixture
    def in_project_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "src").mkdir()
        reset_config()
        return tmp_path

    def test_selects_fork_by_default(self, in_project_dir):
        runner = get_mutant_runner(2)
        assert isinstance(runner, ForkRunner)
        assert runner.max_workers == 2

    def test_selects_forkserver(self, in_project_dir, monkeypatch):
        monkeypatch.setattr(config(), "process_isolation", ProcessIsolation.FORKSERVER)
        runner = get_mutant_runner(4)
        assert isinstance(runner, ForkServerRunner)
        assert runner.max_workers == 4
        assert runner.max_restarts == config().max_forkserver_restarts

    def test_rejects_zero_workers(self, in_project_dir):
        with pytest.raises(ValueError, match="at least 1"):
            get_mutant_runner(0)


@pytest.mark.skipif(os.name == "nt", reason="POSIX pipes required")
class TestPipeMessaging:
    """Framed pipe messages must stay in step with select() on the raw fd.

    A buffered reader can pull several frames into userspace at once, after which
    select() reports "not readable" and the already-received frames are never
    processed - the receiver loops forever waiting for results it already has."""

    def test_roundtrips_a_message(self):
        r, w = os.pipe()
        try:
            send_message(w, ("mod.x_foo__mutmut_1", 0))
            assert recv_message(r) == ("mod.x_foo__mutmut_1", 0)
        finally:
            os.close(r)
            os.close(w)

    def test_reading_one_message_leaves_the_rest_selectable(self):
        import select

        r, w = os.pipe()
        try:
            for i in range(5):
                send_message(w, (f"mod.x_foo__mutmut_{i}", 0))

            assert recv_message(r) == ("mod.x_foo__mutmut_0", 0)
            # The remaining four must still be visible to select(), or the
            # receive loop would block on them forever.
            assert select.select([r], [], [], 0)[0], "remaining messages are not selectable"
            assert [recv_message(r)[0] for _ in range(4)] == [f"mod.x_foo__mutmut_{i}" for i in range(1, 5)]
        finally:
            os.close(r)
            os.close(w)

    def test_survives_a_payload_larger_than_the_pipe_buffer(self):
        # 128k of test ids exceeds both PIPE_BUF and the 64k pipe capacity, so
        # the write must be looped and the read must reassemble it.
        payload = ("mod.x_foo__mutmut_1", [f"tests/test_{i}.py::test_case" for i in range(5000)], 10)
        r, w = os.pipe()
        reader = threading.Thread(target=lambda: received.append(recv_message(r)))
        received: list = []
        try:
            reader.start()
            send_message(w, payload)
            reader.join(timeout=10)
            assert not reader.is_alive(), "receiver blocked on a large message"
            assert received == [payload]
        finally:
            os.close(r)
            os.close(w)

    def test_reports_eof_when_the_writer_closes(self):
        r, w = os.pipe()
        os.close(w)
        try:
            with pytest.raises(EOFError):
                recv_message(r)
        finally:
            os.close(r)


class TestForkServerRunnerNoTestMutants:
    """ForkServerRunner resolves a mutant with no tests the same way ForkRunner does."""

    @staticmethod
    def _runner():
        return ForkServerRunner(max_workers=4, test_runner_class=object, test_runner_args={})

    def test_no_test_mutant_is_resolved_without_a_forkserver(self):
        runner = self._runner()  # never started, so there is no work pipe
        runner.submit("mod.x_foo__mutmut_1", [], cpu_time_limit=1, estimated_time=0.0)
        assert runner.pending_count() == 1

    def test_no_test_mutant_reports_exit_code_33(self):
        runner = self._runner()
        runner.submit("mod.x_foo__mutmut_1", [], cpu_time_limit=1, estimated_time=0.0)
        result = runner.wait_for_result()
        assert (result.mutant_name, result.exit_code) == ("mod.x_foo__mutmut_1", 33)
        assert runner.pending_count() == 0


class _RecordingTestRunner:
    """A TestRunner that records its pid to disk and dirties its own sys.modules.

    The pid file is visible to the parent either way; the marker module only if the
    operation ran in the parent.
    """

    MARKER_MODULE = "imported_by_the_test_runner"
    pid_file = ""  # Set by the test before the operation runs; inherited by the fork.

    def _record(self) -> None:
        sys.modules[self.MARKER_MODULE] = ModuleType(self.MARKER_MODULE)
        Path(self.pid_file).write_text(str(os.getpid()))

    def run_stats(self, tests):
        self._record()
        state().duration_by_test["test_from_the_child"] = 1.5
        state().tests_by_mangled_function_name["mod.x_foo"].add("test_from_the_child")
        return 0

    def run_tests(self, *, mutant_name, tests):
        self._record()
        return 0

    def run_forced_fail(self):
        self._record()
        return 1

    def list_all_tests(self):
        self._record()
        return ListAllTestsResult(ids={"test_from_the_child"})


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestForkServerRunnerNeverRunsTestsInTheMainProcess:
    """Under forkserver, no test execution may happen in the main process.

    A conftest that calls gevent.monkey.patch_all() must not run where we fork from.
    """

    @pytest.fixture(autouse=True)
    def runner(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_RecordingTestRunner, "pid_file", str(tmp_path / "ran_in_pid"))
        self.pid_file = tmp_path / "ran_in_pid"
        reset_state()
        yield
        sys.modules.pop(_RecordingTestRunner.MARKER_MODULE, None)

    def _runner(self):
        return ForkServerRunner(max_workers=1, test_runner_class=_RecordingTestRunner, test_runner_args={})

    def _assert_ran_in_a_child(self):
        assert self.pid_file.exists(), "the operation never ran"
        assert self.pid_file.read_text() != str(os.getpid()), "the operation ran in the main process"
        assert _RecordingTestRunner.MARKER_MODULE not in sys.modules, (
            "the test runner's imports leaked into the main process"
        )

    def test_collect_stats_runs_in_a_child(self):
        assert self._runner().collect_stats(tests=None) == 0
        self._assert_ran_in_a_child()

    def test_collect_stats_still_merges_what_the_child_measured(self):
        self._runner().collect_stats(tests=None)
        # The child cannot touch the parent's state(), so these came back over the pipe.
        assert state().duration_by_test["test_from_the_child"] == 1.5
        assert state().tests_by_mangled_function_name["mod.x_foo"] == {"test_from_the_child"}

    def test_run_clean_tests_runs_in_a_child(self):
        assert self._runner().run_clean_tests(tests=["test_a"]) == 0
        self._assert_ran_in_a_child()

    def test_run_forced_fail_runs_in_a_child(self):
        assert self._runner().run_forced_fail() == 1
        self._assert_ran_in_a_child()

    def test_list_all_tests_runs_in_a_child(self):
        assert self._runner().list_all_tests().ids == {"test_from_the_child"}
        self._assert_ran_in_a_child()

    def test_the_parent_never_holds_a_test_runner_instance(self):
        """The parent keeps the class, so it cannot run tests even by mistake."""
        runner = self._runner()
        assert runner.test_runner_class is _RecordingTestRunner
        assert not any(isinstance(value, _RecordingTestRunner) for value in vars(runner).values())
