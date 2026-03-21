"""
Fork isolation utilities for keeping the parent process clean.

The main process must not import pytest/test code directly, because test
conftest.py files may call gevent.monkey.patch_all() or import grpc, which
makes the process fork-unsafe.

These utilities run operations in forked children so the parent stays clean.
Uses pipe-based IPC for reduced overhead (no temp files, no cleanup needed).
"""

import io
import logging
import os
import pickle
import resource
import select
import signal
import time
import traceback
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty
from time import process_time
from typing import Any
from typing import NamedTuple

from mutmut.models.mutant_status import MutantStatus
from mutmut.runners.harness import TestRunner
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

    # Parent: close write end, wait for child, read result
    os.close(write_fd)
    _, status = os.waitpid(pid, 0)
    exit_code = os.waitstatus_to_exitcode(status)

    # Read result from pipe
    with os.fdopen(read_fd, "rb") as f:
        try:
            data = pickle.load(f)
        except Exception:
            data = None

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

    def __init__(self, exit_code: int, lost_mutants: list[str], crash_log: str | None = None):
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


logger = logging.getLogger(__name__)

_file_handler: logging.Handler | None = None


def setup_file_logging(log_file: str = "mutants/mutmut-debug.log", level: int = logging.DEBUG) -> None:
    """Set up file-based logging for debugging.

    Creates a rotating log file at the specified path. Useful for debugging
    child processes which can't easily log to the console.

    Args:
        log_file: Path to the log file (default: 'mutants/mutmut-debug.log')
        level: Logging level (default: DEBUG)
    """
    global _file_handler

    if _file_handler is not None:
        return

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    _file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
    )
    _file_handler.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(process)d] %(name)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    _file_handler.setFormatter(formatter)

    # Add handler to mutmut logger - file only, no stdout
    root_logger = logging.getLogger("mutmut")
    root_logger.addHandler(_file_handler)
    root_logger.setLevel(level)
    root_logger.propagate = False  # Don't propagate to root logger (avoids stdout)

    logger.debug(f"File logging initialized: {log_path}")


def get_log_file_path(log_dir: str = "mutants") -> Path:
    """Get the path to the debug log file.

    Args:
        log_dir: Directory where log files are stored

    Returns:
        Path to the debug log file
    """
    return Path(log_dir) / "mutmut-debug.log"


@dataclass
class MutantResult:
    """Result of testing a single mutant."""

    mutant_name: str
    exit_code: int
    status: MutantStatus
    duration: float
    output: str | None = None


class ActiveWorker(NamedTuple):
    """Info about an active worker for timeout checking."""

    pid: int
    start_time: datetime
    mutant_name: str
    estimated_time: float


class MutantRunner(ABC):
    """Abstract base class for mutation test runners.

    Runners handle the process isolation strategy for running tests against
    mutants.

    Usage:
        runner = get_runner(config)
        runner.startup(max_children)

        for mutant in mutants:
            while not runner.has_capacity():
                result = runner.wait_for_result(timeout)
                register_result(result)
            runner.submit(mutant_name, tests, cpu_time_limit, estimated_time)

        while runner.pending_count() > 0:
            result = runner.wait_for_result(timeout)
            register_result(result)

        runner.shutdown()
    """

    @abstractmethod
    def startup(self, max_children: int) -> None:
        """Called once before mutation testing begins.

        Args:
            max_children: Maximum number of concurrent workers.
        """

    @abstractmethod
    def submit(self, mutant_name: str, tests: list[str], cpu_time_limit: int, estimated_time: float) -> None:
        """Submit a mutant for testing. Non-blocking.

        Args:
            mutant_name: The mutant identifier (e.g., 'module.func__mutmut_1')
            tests: List of test paths to run (pre-sorted by duration, fast first)
            cpu_time_limit: CPU time limit in seconds for the test run
            estimated_time: Estimated test duration for timeout tracking
        """

    @abstractmethod
    def has_capacity(self) -> bool:
        """True if we can submit more work without exceeding max workers."""

    @abstractmethod
    def wait_for_result(self, timeout: float | None = None) -> MutantResult:
        """Block until one result is available.

        Args:
            timeout: Max seconds to wait. Should be max expected test duration.
                     If None, blocks indefinitely.

        Returns:
            MutantResult for a completed mutant test.
        """

    @abstractmethod
    def pending_count(self) -> int:
        """Number of in-flight mutants awaiting results."""

    @abstractmethod
    def get_active_workers(self) -> list[ActiveWorker]:
        """Return active workers for timeout checking.

        Returns:
            List of ActiveWorker tuples for each worker currently running a test.
        """

    @abstractmethod
    def signal_work_complete(self) -> None:
        """Signal that no more work will be submitted.

        Called after all mutants have been submitted but before waiting
        for final results. For runners with coordinator processes (like
        HotForkRunner), this closes the work pipe to signal EOF.

        Default implementation is a no-op for runners that don't need it.
        """

    def get_orchestrator_restart_count(self) -> int:
        """Return the number of times the orchestrator was restarted due to crashes.

        Only meaningful for HotForkRunner. Other runners return 0.

        Returns:
            Number of orchestrator restarts (0 means no crashes).
        """
        return 0

    @abstractmethod
    def shutdown(self) -> None:
        """Called after all mutants tested. Clean up resources."""


class HotForkRunner(MutantRunner):
    """Fork-safe mutation runner using single hot orchestrator.

    Architecture:
        Parent (clean) → Orchestrator (imports pytest) → N concurrent children

    The parent never imports pytest/conftest, staying fork-safe.
    The orchestrator imports pytest once, then forks per mutant.
    Grandchildren run individual tests and exit.

    This is faster than SubprocessPoolRunner (1 pytest import vs N)
    and compatible with fork-unsafe libraries like gevent/grpc.
    """

    class RunningChild(NamedTuple):
        """Info about a running child process."""

        mutant_name: str
        start_time: float
        wall_timeout: float

    # Default maximum number of orchestrator restarts before giving up
    DEFAULT_MAX_RESTARTS = 3

    def __init__(
        self,
        max_workers: int,
        test_runner_class: type,
        test_runner_args: dict[str, Any],
        debug: bool = False,
        max_restarts: int | None = None,
    ):
        self.max_workers = max_workers
        self.test_runner_class = test_runner_class
        self.test_runner_args = test_runner_args
        self.debug = debug
        self.max_restarts = max_restarts if max_restarts is not None else self.DEFAULT_MAX_RESTARTS

        self.work_pipe_read: int | None = None
        self.work_pipe_write: int | None = None
        self.result_pipe_read: int | None = None
        self.result_pipe_write: int | None = None

        self.orchestrator_pid: int | None = None
        self._pending: set[str] = set()  # mutant_names in flight
        # mutant_name -> (tests, cpu_time_limit, estimated_time, start_time)
        self._pending_work: dict[str, tuple[list[str], int, float, datetime]] = {}
        self._result_file: io.BufferedReader | None = None
        self._shutting_down = False
        self._restart_count = 0
        self._crash_exit_codes: list[int] = []

    def startup(self, max_children: int | None = None) -> None:
        """Fork the orchestrator process.

        Args:
            max_children: Ignored (uses self.max_workers from __init__).
                          Present for MutantRunner ABC compatibility.
        """
        self._start_orchestrator()

    def _start_orchestrator(self) -> None:
        """Fork a new orchestrator process.

        Creates pipes and forks the orchestrator. Can be called multiple times
        for crash recovery - each call creates fresh pipes and a new orchestrator.
        """
        # Close any existing result file from previous orchestrator
        if self._result_file is not None:
            try:
                self._result_file.close()
            except Exception:
                pass
            self._result_file = None

        # Create pipes for bidirectional communication
        self.work_pipe_read, self.work_pipe_write = os.pipe()
        self.result_pipe_read, self.result_pipe_write = os.pipe()

        pid = os.fork()
        if pid == 0:
            # Child: become orchestrator
            os.close(self.work_pipe_write)
            os.close(self.result_pipe_read)
            try:
                self._orchestrator_main(self.work_pipe_read, self.result_pipe_write)
            except Exception as e:
                self._write_crash_log(e)
                os._exit(1)
            os._exit(0)

        # Parent: close child's ends
        os.close(self.work_pipe_read)
        os.close(self.result_pipe_write)
        self.orchestrator_pid = pid
        logger.info(f"HotForkRunner started orchestrator (pid={pid})")

    def _restart_orchestrator_with_pending_work(self, exit_code: int = -1) -> None:
        """Restart orchestrator and re-submit all pending work.

        Called when orchestrator crash is detected. Increments restart counter
        and raises OrchestratorCrashError if max restarts exceeded.

        Args:
            exit_code: The exit code from the crashed orchestrator (-1 if unknown).
        """
        self._restart_count += 1
        self._crash_exit_codes.append(exit_code)

        # Log detailed crash info including pending mutants
        crash_log_path = get_log_file_path().parent / ".orchestrator-crash.log"
        pending_mutants = list(self._pending)
        logger.error(
            f"Orchestrator crashed with exit code {exit_code}. "
            f"Check {crash_log_path} and {get_log_file_path()} for details."
        )
        logger.error(f"Pending mutants at time of crash ({len(pending_mutants)}): {pending_mutants}")

        if self._restart_count > self.max_restarts:
            crash_log = get_log_file_path().parent / ".orchestrator-crash.log"
            raise OrchestratorCrashError(
                exit_code=-1, lost_mutants=list(self._pending), crash_log=str(crash_log) if crash_log.exists() else None
            )

        lost_count = len(self._pending)
        logger.warning(
            f"Orchestrator crashed, restarting (attempt {self._restart_count}/{self.max_restarts}), "
            f"re-submitting {lost_count} pending mutant(s)"
        )

        # Save pending work before restarting (will be re-submitted)
        pending_work_copy = dict(self._pending_work)

        self._start_orchestrator()

        # Re-submit all pending work to the new orchestrator
        if self.work_pipe_write is None:
            raise RuntimeError("Failed to restart orchestrator - work pipe not created")
        for mutant_name, (tests, cpu_time_limit, estimated_time, _) in pending_work_copy.items():
            msg = (mutant_name, list(tests), cpu_time_limit)
            data = pickle.dumps(msg)
            os.write(self.work_pipe_write, data)
            # Update start time to now
            self._pending_work[mutant_name] = (tests, cpu_time_limit, estimated_time, datetime.now())
            logger.debug(f"Re-submitted {mutant_name} to new orchestrator")

        logger.info(f"Orchestrator restarted, {lost_count} mutant(s) re-submitted")

    def _write_crash_log(self, exception: Exception) -> None:
        """Write crash information for debugging.

        Uses get_log_file_path() pattern for consistency.
        """
        crash_file = get_log_file_path().parent / ".orchestrator-crash.log"
        try:
            crash_file.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "w") as f:
                f.write(f"Orchestrator crash at {datetime.now()}\n")
                f.write(f"Exception: {exception}\n")
                f.write(traceback.format_exc())
        except Exception:
            pass  # Best effort logging

    def _setup_sigchld_pipe(self) -> tuple[int, int]:
        """Set up SIGCHLD notification via self-pipe for efficient child reaping.

        Returns:
            Tuple of (read_fd, write_fd) for the notification pipe.
        """
        sigchld_pipe_r, sigchld_pipe_w = os.pipe()
        os.set_blocking(sigchld_pipe_r, False)
        os.set_blocking(sigchld_pipe_w, False)

        def sigchld_handler(signum: int, frame: Any) -> None:
            # Write a byte to wake up select() - ignore errors (pipe full is fine)
            try:
                os.write(sigchld_pipe_w, b"c")
            except (BlockingIOError, OSError):
                pass

        signal.signal(signal.SIGCHLD, sigchld_handler)
        return sigchld_pipe_r, sigchld_pipe_w

    def _wait_for_child_event(self, sigchld_pipe_r: int, timeout: float | None) -> bool:
        """Wait for a child to exit or timeout.

        Args:
            sigchld_pipe_r: Read end of the SIGCHLD notification pipe.
            timeout: Max seconds to wait, or None to block indefinitely.

        Returns:
            True if a child may be ready to reap, False on timeout.
        """
        try:
            readable, _, _ = select.select([sigchld_pipe_r], [], [], timeout)
            if readable:
                # Drain all notifications from the pipe
                try:
                    while os.read(sigchld_pipe_r, 1024):
                        pass
                except BlockingIOError:
                    pass  # Expected when pipe is drained
                return True
            return False  # Timeout
        except InterruptedError:
            return True  # Signal interrupted, check anyway

    def _orchestrator_main(self, work_fd: int, result_fd: int) -> None:
        """Orchestrator: import pytest once, then fork per mutant."""
        # Ignore SIGINT - parent handles shutdown
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        setup_file_logging()
        orchestrator_logger = logging.getLogger("mutmut.hotfork.orchestrator")
        orchestrator_logger.info(f"Hot-fork orchestrator starting (pid={os.getpid()})")

        test_runner: TestRunner = self.test_runner_class(**self.test_runner_args)

        test_runner.warm_up()
        orchestrator_logger.info("Test runner initialized, ready for work")

        # Set up SIGCHLD notification pipe for efficient child reaping
        # IMPORTANT: This must be AFTER test_runner.warm_up() because
        # libraries like gevent may monkey-patch signals during import/setup.
        sigchld_pipe_r, sigchld_pipe_w = self._setup_sigchld_pipe()
        orchestrator_logger.debug("SIGCHLD notification pipe set up")

        work_file = os.fdopen(work_fd, "rb")
        result_file = os.fdopen(result_fd, "wb", buffering=0)

        running: dict[int, HotForkRunner.RunningChild] = {}

        while True:
            self._reap_children(running, result_file, orchestrator_logger, sigchld_pipe_r, block=False)

            while len(running) >= self.max_workers:
                self._reap_children(running, result_file, orchestrator_logger, sigchld_pipe_r, block=True, timeout=1.0)

            readable, _, _ = select.select([work_fd, sigchld_pipe_r], [], [], 1.0)

            if sigchld_pipe_r in readable:
                self._reap_children(running, result_file, orchestrator_logger, sigchld_pipe_r, block=False)

            if work_fd not in readable:
                continue

            try:
                msg = pickle.load(work_file)
            except EOFError:
                break

            if msg is None:
                break

            mutant_name, tests, cpu_time_limit = msg
            # Wall-clock timeout should be shorter than CPU limit because:
            # - Multi-threaded code can use more CPU time than wall time
            # - Wall time is actual elapsed time; CPU time is sum across cores
            # Use half of CPU limit as wall timeout
            wall_timeout = cpu_time_limit / 2
            orchestrator_logger.debug(
                f"Received mutant: {mutant_name} ({len(tests)} tests, cpu_limit={cpu_time_limit}s, wall_timeout={wall_timeout}s)"
            )

            # Fork child for this mutant
            child_pid = os.fork()
            if child_pid == 0:
                # Grandchild: run test with CPU limit
                worker_logger = logging.getLogger(f"mutmut.hotfork.worker.{os.getpid()}")
                worker_logger.debug(f"Starting {mutant_name} ({len(tests)} tests)")

                # Suppress stdout/stderr to avoid breaking terminal output
                import sys

                sys.stdout = sys.stderr = open(os.devnull, "w")

                limit = cpu_time_limit + int(process_time())
                resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 1))

                os.environ["MUTANT_UNDER_TEST"] = mutant_name
                try:
                    exit_code = test_runner.run_tests(mutant_name=mutant_name, tests=tests)
                except Exception as e:
                    worker_logger.error(f"Exception running {mutant_name}: {e}")
                    exit_code = -1

                status_name = MutantStatus.from_exit_code(exit_code).text
                worker_logger.debug(f"Finished {mutant_name}: {status_name} (exit={exit_code})")
                os._exit(exit_code)

            running[child_pid] = self.RunningChild(mutant_name, time.time(), wall_timeout)
            # Register wall-clock timeout - background thread will send SIGXCPU on expiry
            register_timeout(child_pid, wall_timeout)

        orchestrator_logger.info("Work queue exhausted, waiting for remaining children")
        # Wait for remaining children
        while running:
            self._reap_children(running, result_file, orchestrator_logger, sigchld_pipe_r, block=True, timeout=1.0)

        # Clean up SIGCHLD pipe
        try:
            os.close(sigchld_pipe_r)
            os.close(sigchld_pipe_w)
        except OSError:
            pass
        orchestrator_logger.info("Orchestrator shutting down cleanly")

    def _reap_children(
        self,
        running: dict[int, RunningChild],
        result_file: io.FileIO,
        orchestrator_logger: logging.Logger,
        sigchld_pipe_r: int,
        block: bool,
        timeout: float | None = None,
    ) -> None:
        """Reap completed children and write results.

        Args:
            running: Dict of pid -> RunningChild
            result_file: File to write results to
            orchestrator_logger: Logger instance
            sigchld_pipe_r: Read end of SIGCHLD notification pipe
            block: If True, block until a child exits (or timeout)
            timeout: If blocking, max seconds to wait before returning
        """
        if block:
            # Wait for SIGCHLD notification or timeout (event-driven, no polling)
            if not self._wait_for_child_event(sigchld_pipe_r, timeout):
                return  # Timeout reached, no child ready

        # IMPORTANT: Reap ALL ready children in a loop.
        # SIGCHLD can be coalesced by the kernel - if multiple children exit
        # before the signal is delivered, we only get one SIGCHLD. If we only
        # reap one child per signal, we can miss children and hang forever
        # waiting on select() for a signal that will never come.
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return  # No children
            if pid == 0:
                return  # No more children ready

            # Handle unknown PIDs gracefully - could be from coverage, pytest
            # plugins, or other subprocesses spawned during test runs
            if pid not in running:
                continue  # Unknown child, keep reaping

            child = running.pop(pid)
            exit_code = os.waitstatus_to_exitcode(status)
            duration = time.time() - child.start_time
            status_name = MutantStatus.from_exit_code(exit_code).text
            orchestrator_logger.debug(
                f"Completed {child.mutant_name}: {status_name} (exit={exit_code}, {duration:.3f}s)"
            )
            pickle.dump((child.mutant_name, exit_code), result_file)

    def submit(self, mutant_name: str, tests: list[str], cpu_time_limit: int, estimated_time: float) -> None:
        """Send work to orchestrator.

        Args:
            mutant_name: The mutant identifier.
            tests: List of test paths to run.
            cpu_time_limit: CPU time limit in seconds.
            estimated_time: Estimated test duration for timeout tracking.
        """
        if self.work_pipe_write is None:
            raise RuntimeError("HotForkRunner not started - call startup() first")
        msg = (mutant_name, list(tests), cpu_time_limit)
        data = pickle.dumps(msg)
        os.write(self.work_pipe_write, data)
        self._pending.add(mutant_name)
        self._pending_work[mutant_name] = (list(tests), cpu_time_limit, estimated_time, datetime.now())

    def has_capacity(self) -> bool:
        """Check if we can submit more work."""
        return len(self._pending) < self.max_workers

    def signal_work_complete(self) -> None:
        """Signal to orchestrator that no more work will be submitted.

        This closes the work pipe, causing the orchestrator to get EOF and
        begin draining remaining workers. Must be called after all work
        is submitted and before waiting for final results.
        """
        if self.work_pipe_write is None:
            return
        try:
            os.close(self.work_pipe_write)
            self.work_pipe_write = None
            logger.debug("Work pipe closed, orchestrator will drain remaining workers")
        except OSError:
            self.work_pipe_write = None

    def _check_orchestrator_alive(self) -> None:
        """Check if orchestrator is still running, restart if crashed.

        If the orchestrator has crashed (non-zero exit), this method will:
        1. Reap the dead orchestrator process
        2. Start a new orchestrator
        3. Re-submit all pending work

        If the orchestrator exited cleanly (exit code 0), we don't restart.

        Raises:
            OrchestratorCrashError: If max restart attempts exceeded.
        """
        if self.orchestrator_pid is None:
            return
        try:
            pid, status = os.waitpid(self.orchestrator_pid, os.WNOHANG)
            if pid == self.orchestrator_pid:
                exit_code = os.waitstatus_to_exitcode(status)
                self.orchestrator_pid = None

                if exit_code == 0:
                    logger.debug(f"Orchestrator (pid={pid}) exited cleanly")
                    return

                logger.warning(f"Orchestrator (pid={pid}) crashed with exit code {exit_code}")
                self._restart_orchestrator_with_pending_work(exit_code=exit_code)
        except ChildProcessError:
            logger.warning("Orchestrator process not found")
            self.orchestrator_pid = None
            self._restart_orchestrator_with_pending_work(exit_code=-1)

    def wait_for_result(self, timeout: float | None = None) -> MutantResult:
        """Read one result from orchestrator, with crash detection."""
        if self.result_pipe_read is None:
            raise RuntimeError("HotForkRunner not started - call startup() first")
        while True:
            self._check_orchestrator_alive()

            r, _, _ = select.select([self.result_pipe_read], [], [], timeout or 1.0)
            if not r:
                if timeout is not None:
                    raise Empty()
                continue

            if self._result_file is None:
                self._result_file = os.fdopen(self.result_pipe_read, "rb")

            try:
                mutant_name, exit_code = pickle.load(self._result_file)
            except EOFError as err:
                self._check_orchestrator_alive()
                raise OrchestratorCrashError(exit_code=-1, lost_mutants=list(self._pending), crash_log=None) from err

            self._pending.discard(mutant_name)
            self._pending_work.pop(mutant_name, None)

            return MutantResult(
                mutant_name=mutant_name,
                exit_code=exit_code,
                status=MutantStatus.from_exit_code(exit_code),
                duration=0,
            )

    def pending_count(self) -> int:
        """Return number of mutants in flight."""
        return len(self._pending)

    def get_orchestrator_restart_count(self) -> int:
        """Return the number of times the orchestrator was restarted due to crashes."""
        return self._restart_count

    def get_orchestrator_crash_details(self) -> tuple[list[int], Path | None, Path | None]:
        """Return details about orchestrator crashes for user notification.

        Returns:
            Tuple of (exit_codes, crash_log_path, debug_log_path) where:
            - exit_codes: List of exit codes from each crash
            - crash_log_path: Path to orchestrator crash log (if exists)
            - debug_log_path: Path to main debug log (if exists)
        """
        crash_log = get_log_file_path().parent / ".orchestrator-crash.log"
        debug_log = get_log_file_path()
        return (
            self._crash_exit_codes,
            crash_log if crash_log.exists() else None,
            debug_log if debug_log.exists() else None,
        )

    def get_active_workers(self) -> list[ActiveWorker]:
        """Return active workers for timeout checking.

        Note: Since the orchestrator manages grandchildren, we can only report
        what we know from the parent side (pending mutants with their start times).
        The orchestrator PID is used as a proxy since we can't see grandchild PIDs.

        Returns:
            List of ActiveWorker for each pending mutant.
        """
        if not self.orchestrator_pid:
            return []
        return [
            ActiveWorker(self.orchestrator_pid, start_time, mutant_name, estimated_time)
            for mutant_name, (_, _, estimated_time, start_time) in self._pending_work.items()
        ]

    def shutdown(self) -> None:
        """Close work pipe and wait for orchestrator.

        Prioritizes clean shutdown to ensure all completed results are recorded.
        Called automatically on SIGINT if _shutting_down flag is respected.
        """
        if self._shutting_down:
            return
        self._shutting_down = True

        logger.info("HotForkRunner shutting down")

        self.signal_work_complete()

        # Drain remaining results before waiting for orchestrator
        # This ensures we capture all completed work
        while self._pending:
            try:
                result = self.wait_for_result(timeout=1.0)
                # Results should be recorded by caller, but we still drain
                self._pending.discard(result.mutant_name)
                self._pending_work.pop(result.mutant_name, None)
            except Empty:
                break
            except OrchestratorCrashError:
                break

        if self.orchestrator_pid:
            try:
                os.waitpid(self.orchestrator_pid, 0)
            except ChildProcessError:
                pass

        if self._result_file:
            try:
                self._result_file.close()
            except Exception:
                pass
        elif self.result_pipe_read is not None:
            try:
                os.close(self.result_pipe_read)
            except OSError:
                pass

        logger.info("HotForkRunner shutdown complete")
