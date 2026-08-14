"""Tests for fork isolation utilities."""

import os

import pytest

from mutmut.workers.isolation import ForkRunner
from mutmut.workers.isolation import OrchestratorCrashError
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
