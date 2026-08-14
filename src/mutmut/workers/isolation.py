"""
Fork isolation utilities and mutation-test runners.

The main process must not import pytest/test code directly, because test
conftest.py files may call gevent.monkey.patch_all() or import grpc, which
makes the process fork-unsafe.

The low-level ``run_in_fork*`` helpers run operations in forked children so the
parent stays clean. On top of them, ``MutantRunner`` abstracts the process
isolation strategy used to test each mutant. ``ForkRunner`` is the traditional
os.fork()-per-mutant approach; ``HotForkRunner`` (single orchestrator) will be
layered on later for fork-unsafe libraries.
"""

from __future__ import annotations

import gc
import os
import pickle
import resource
import signal
import sys
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from time import process_time
from typing import Any
from typing import NamedTuple

from mutmut.configuration import ProcessIsolation
from mutmut.configuration import config
from mutmut.mutation.trampoline import set_mutant_under_test
from mutmut.runners.harness import ListAllTestsResult
from mutmut.runners.harness import PytestRunner
from mutmut.runners.harness import TestRunner
from mutmut.state import state
from mutmut.utils.safe_setproctitle import safe_setproctitle as setproctitle
from mutmut.workers.timeout import register_timeout


def run_in_fork_with_result(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Fork a child to run a function, return its result via pipe.

    The parent process stays clean - child's imports don't affect parent.
    Uses os.pipe() for IPC - lower overhead than temp files.

    Args:
        fn: Function that returns a picklable result.
        *args, **kwargs: Arguments to pass to fn.

    Returns:
        The return value of fn(*args, **kwargs).

    Raises:
        ChildProcessError: If child exits with non-zero status.
    """
    # Create pipe for result transfer
    read_fd, write_fd = os.pipe()

    pid = os.fork()
    if pid == 0:
        # Child: close read end, run function, write result
        os.close(read_fd)
        try:
            result = fn(*args, **kwargs)
            with os.fdopen(write_fd, "wb") as f:
                pickle.dump({"ok": True, "value": result}, f)
            os._exit(0)
        except Exception as e:
            try:
                with os.fdopen(write_fd, "wb") as f:
                    pickle.dump({"ok": False, "error": str(e)}, f)
            except Exception:
                pass
            os._exit(1)

    # Parent: close write end, read result BEFORE waiting for the child.
    # IMPORTANT: read before waitpid to avoid deadlock. If the pickled data
    # exceeds the pipe buffer (~64KB) the child blocks on write until the parent
    # reads; if the parent waits on the child first that is a deadlock.
    os.close(write_fd)

    with os.fdopen(read_fd, "rb") as f:
        try:
            data = pickle.load(f)
        except Exception:
            data = None

    _, status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(status)

    if exit_code != 0 or data is None:
        error_msg = f"Child exited with code {exit_code}"
        if data and not data.get("ok") and "error" in data:
            error_msg += f": {data['error']}"
        raise ChildProcessError(error_msg)

    if not data.get("ok"):
        raise ChildProcessError(f"Child failed: {data.get('error', 'unknown')}")

    return data["value"]


def run_in_fork(fn: Callable[..., int], *args: Any, **kwargs: Any) -> int:
    """Fork a child to run a function, return its exit code.

    Use for operations that only need pass/fail result (clean test, forced fail).
    Parent process stays clean - child's imports don't affect parent.

    Args:
        fn: Function that returns an exit code (0-255).
        *args, **kwargs: Arguments to pass to fn.

    Returns:
        Exit code from the child process.
    """
    pid = os.fork()
    if pid == 0:
        # Child: run function and exit with its return code
        try:
            exit_code = fn(*args, **kwargs)
            os._exit(exit_code if isinstance(exit_code, int) else 0)
        except Exception:
            os._exit(1)

    # Parent waits for child
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


class OrchestratorCrashError(Exception):
    """Raised when the hot-fork orchestrator crashes unexpectedly.

    The orchestrator manages all mutant test runs. If it crashes, any
    in-flight mutants are lost. The user can resume by running
    `mutmut run` again - completed results are preserved.
    """

    def __init__(self, exit_code: int, lost_mutants: list[str], crash_log: str | None = None) -> None:
        self.exit_code = exit_code
        self.lost_mutants = lost_mutants
        self.crash_log = crash_log

        # Build detailed message
        details = [
            f"Hot-fork orchestrator crashed unexpectedly (exit code: {exit_code})",
            f"Lost {len(lost_mutants)} in-flight mutant(s):",
        ]
        for m in lost_mutants[:10]:
            details.append(f"  - {m}")
        if len(lost_mutants) > 10:
            details.append(f"  ... and {len(lost_mutants) - 10} more")

        details.append("")
        details.append("This usually indicates a bug in pytest or conftest.py.")
        if crash_log:
            details.append(f"Crash log: {crash_log}")
        details.append("")
        details.append("To resume: mutmut run")
        details.append("(Completed mutants are saved; lost ones will be re-run)")

        super().__init__("\n".join(details))


@dataclass
class MutantResult:
    """Result of testing a single mutant."""

    mutant_name: str
    exit_code: int
    duration: float


class RunningWorker(NamedTuple):
    """Tracks an in-flight mutation-test worker for ForkRunner."""

    mutant_name: str
    start_time: datetime
    estimated_time: float


class MutantRunner(ABC):
    """Abstract base class for mutation-test runners.

    A runner owns the process-isolation strategy for testing mutants and also
    exposes the surrounding test operations (stats collection, clean tests,
    forced-fail, test listing) so the caller never has to touch a raw test
    runner directly.

    Usage::

        runner = get_mutant_runner(max_children)
        runner.startup()
        for mutant in mutants:
            while not runner.has_capacity():
                register_result(runner.wait_for_result())
            runner.submit(mutant_name, tests, cpu_time_limit, estimated_time)
        runner.signal_work_complete()
        while runner.pending_count() > 0:
            register_result(runner.wait_for_result())
        runner.shutdown()
    """

    @abstractmethod
    def startup(self) -> None:
        """Called once before mutation testing begins."""

    @abstractmethod
    def submit(self, mutant_name: str, tests: list[str], cpu_time_limit: int, estimated_time: float) -> None:
        """Submit a mutant for testing.

        Does not wait for the result, but may block while handing the work off
        if the runner's intake is full.

        Args:
            mutant_name: The mutant identifier (e.g. 'module.func__mutmut_1').
            tests: Test node ids to run.
            cpu_time_limit: CPU-time limit in seconds for the test run.
            estimated_time: Estimated test duration, used for timeout tracking.
        """

    @abstractmethod
    def has_capacity(self) -> bool:
        """True if we can submit more work without exceeding max workers."""

    @abstractmethod
    def wait_for_result(self, timeout: float | None = None) -> MutantResult:
        """Block until one result is available and return it."""

    @abstractmethod
    def pending_count(self) -> int:
        """Number of in-flight mutants awaiting results."""

    @abstractmethod
    def signal_work_complete(self) -> None:
        """Signal that no more work will be submitted.

        Called after all mutants have been submitted but before waiting for the
        final results. Runners with a coordinator process use this to close the
        work pipe; others treat it as a no-op.
        """

    def stop_all_workers(self) -> None:
        """Terminate all in-flight workers (best effort). Default is a no-op."""

    @abstractmethod
    def shutdown(self) -> None:
        """Called after all mutants are tested. Clean up resources."""

    @abstractmethod
    def collect_stats(self, tests: Iterable[str] | None) -> int:
        """Run stats collection. Returns an exit code."""

    @abstractmethod
    def run_clean_tests(self, tests: Iterable[str]) -> int:
        """Run the clean (unmutated) tests. Returns an exit code."""

    @abstractmethod
    def run_forced_fail(self) -> int:
        """Run the forced-fail test. Returns an exit code."""

    @abstractmethod
    def list_all_tests(self) -> ListAllTestsResult:
        """List all tests in the test suite."""


class ForkRunner(MutantRunner):
    """Runner that uses os.fork() for process isolation.

    This is the traditional mutmut approach - fast, but it can misbehave with
    libraries like gevent, grpc, and torch when forking from a parent process
    that has already imported test code. For those, use HotForkRunner instead.
    """

    def __init__(self, max_workers: int, test_runner: TestRunner, debug: bool = False) -> None:
        self.max_workers = max_workers
        self.test_runner = test_runner
        self.debug = debug
        self._running: dict[int, RunningWorker] = {}  # pid -> RunningWorker
        self._no_tests_results: list[MutantResult] = []

    def startup(self) -> None:
        # Freeze the GC so the forked children inherit a stable heap and do not
        # thrash collecting objects the parent already owns.
        gc.freeze()

    def submit(self, mutant_name: str, tests: list[str], cpu_time_limit: int, estimated_time: float) -> None:
        if not tests:
            self._no_tests_results.append(MutantResult(mutant_name=mutant_name, exit_code=33, duration=0.0))
            return

        pid = os.fork()
        if pid == 0:
            # In the child.
            set_mutant_under_test(mutant_name)
            setproctitle(f"mutmut: {mutant_name}")

            # Run fast tests first.
            tests_sorted = sorted(tests, key=lambda test_name: state().duration_by_test[test_name])

            # Signal SIGXCPU after the CPU limit, and SIGKILL one second later if
            # it is still running.
            limit = cpu_time_limit + int(process_time())
            resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 1))

            if not self.debug:
                sys.stdout = sys.stderr = open(os.devnull, "w")

            result = self.test_runner.run_tests(mutant_name=mutant_name, tests=tests_sorted)
            os._exit(result)
        else:
            # In the parent.
            cfg = config()
            wall_time_limit_s = (estimated_time + cfg.timeout_constant) * cfg.timeout_multiplier
            register_timeout(pid=pid, timeout_s=wall_time_limit_s)
            self._running[pid] = RunningWorker(mutant_name, datetime.now(), estimated_time)

    def has_capacity(self) -> bool:
        return len(self._running) < self.max_workers

    def wait_for_result(self, timeout: float | None = None) -> MutantResult:
        if self._no_tests_results:
            return self._no_tests_results.pop(0)

        pid, wait_status = os.wait()
        exit_code = os.waitstatus_to_exitcode(wait_status)

        worker = self._running.pop(pid)
        duration = (datetime.now() - worker.start_time).total_seconds()
        return MutantResult(mutant_name=worker.mutant_name, exit_code=exit_code, duration=duration)

    def pending_count(self) -> int:
        # Queued no-test results count as pending: they are submitted work that
        # nobody has collected yet, even though they never occupied a worker slot.
        return len(self._running) + len(self._no_tests_results)

    def signal_work_complete(self) -> None:
        """No-op for ForkRunner (there is no orchestrator to signal)."""

    def stop_all_workers(self) -> None:
        for pid in list(self._running):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def shutdown(self) -> None:
        while self._running:
            try:
                self.wait_for_result()
            except ChildProcessError:
                break
        gc.unfreeze()

    def collect_stats(self, tests: Iterable[str] | None) -> int:
        # Already in a clean process, so run stats directly without forking.
        return self.test_runner.run_stats(tests=tests or [])

    def run_clean_tests(self, tests: Iterable[str]) -> int:
        return self.test_runner.run_tests(mutant_name=None, tests=tests)

    def run_forced_fail(self) -> int:
        return self.test_runner.run_forced_fail()

    def list_all_tests(self) -> ListAllTestsResult:
        return self.test_runner.list_all_tests()


def get_mutant_runner(max_workers: int = 1) -> MutantRunner:
    """Create a MutantRunner based on the configured ``process_isolation``.

    Args:
        max_workers: Maximum number of concurrent workers.

    Returns:
        A MutantRunner instance.
    """
    if max_workers < 1:
        raise ValueError("max_workers must be at least 1")

    if config().process_isolation == ProcessIsolation.HOT_FORK:
        raise NotImplementedError("process_isolation = 'hot-fork' is not available yet in this build; use 'fork'.")

    pytest_runner = PytestRunner()
    pytest_runner.prepare_main_test_run()
    return ForkRunner(max_workers=max_workers, test_runner=pytest_runner, debug=config().debug)
