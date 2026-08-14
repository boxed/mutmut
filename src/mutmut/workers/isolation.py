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
import logging
import os
import pickle
import resource
import select
import signal
import struct
import sys
import time
import traceback
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from queue import Empty
from time import process_time
from typing import Any
from typing import NamedTuple

from mutmut.configuration import ProcessIsolation
from mutmut.configuration import config
from mutmut.models.results import StatsResult
from mutmut.mutation.trampoline import set_mutant_under_test
from mutmut.runners.harness import ListAllTestsResult
from mutmut.runners.harness import PytestRunner
from mutmut.runners.harness import TestRunner
from mutmut.state import state
from mutmut.utils.logging_utils import get_log_file_path
from mutmut.utils.logging_utils import get_logger
from mutmut.utils.logging_utils import setup_file_logging
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


# Pipe messaging. Length-prefixed frames read with raw os.read() rather than a
# buffered reader: the receivers select() on the raw fd, and a buffered reader
# can pull several frames into userspace at once, after which select() reports
# "not readable" and the already-received frames are never processed.
def _write_all(fd: int, data: bytes) -> None:
    """Write every byte, looping over short writes."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def _read_exactly(fd: int, size: int) -> bytes:
    """Read exactly ``size`` bytes. Raises EOFError if the pipe closes first."""
    chunks = bytearray()
    while len(chunks) < size:
        chunk = os.read(fd, size - len(chunks))
        if not chunk:
            raise EOFError("pipe closed mid-message" if chunks else "pipe closed")
        chunks += chunk
    return bytes(chunks)


def send_message(fd: int, payload: Any) -> None:
    """Send one length-prefixed pickled message."""
    body = pickle.dumps(payload)
    _write_all(fd, struct.pack("!I", len(body)) + body)


def recv_message(fd: int) -> Any:
    """Receive one length-prefixed pickled message. Raises EOFError at EOF."""
    (size,) = struct.unpack("!I", _read_exactly(fd, 4))
    return pickle.loads(_read_exactly(fd, size))


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


class HotForkRunner(MutantRunner):
    """Fork-safe mutation runner using a single hot orchestrator.

    Architecture::

        Parent (clean) -> Orchestrator (imports pytest) -> N concurrent children

    The parent never imports pytest/conftest, so it stays fork-safe. The
    orchestrator imports pytest exactly once, then forks a grandchild per
    mutant; each grandchild runs one mutant's tests and exits. This is both
    faster than forking a fresh pytest per mutant (one import instead of N) and
    compatible with fork-unsafe libraries like gevent, grpc, and torch.

    If the orchestrator crashes, in-flight mutants are re-submitted to a fresh
    orchestrator up to ``max_restarts`` times before an OrchestratorCrashError
    is raised.
    """

    class RunningChild(NamedTuple):
        """Info about a grandchild currently running a mutant's tests."""

        mutant_name: str
        start_time: float
        wall_timeout: float

    # Default maximum number of orchestrator restarts before giving up.
    DEFAULT_MAX_RESTARTS = 3

    def __init__(
        self,
        max_workers: int,
        test_runner_class: type,
        test_runner_args: dict[str, Any],
        debug: bool = False,
        max_restarts: int | None = None,
    ) -> None:
        self._logger = get_logger(__name__)
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
        self._shutting_down = False
        self._restart_count = 0
        self._crash_exit_codes: list[int] = []
        self._no_tests_results: list[MutantResult] = []

    def startup(self) -> None:
        gc.freeze()
        self._start_orchestrator()

    def _start_orchestrator(self) -> None:
        """Fork a fresh orchestrator process with new pipes.

        Can be called more than once for crash recovery; each call creates fresh
        pipes and a new orchestrator.
        """
        self.work_pipe_read, self.work_pipe_write = os.pipe()
        self.result_pipe_read, self.result_pipe_write = os.pipe()

        pid = os.fork()
        if pid == 0:
            # Child: become the orchestrator.
            os.close(self.work_pipe_write)
            os.close(self.result_pipe_read)
            try:
                self._orchestrator_main(self.work_pipe_read, self.result_pipe_write)
            except Exception as e:
                self._write_crash_log(e)
                os._exit(1)
            os._exit(0)

        # Parent: close the child's ends.
        os.close(self.work_pipe_read)
        os.close(self.result_pipe_write)
        self.orchestrator_pid = pid
        self._logger.info(f"HotForkRunner started orchestrator (pid={pid})")

    def _restart_orchestrator_with_pending_work(self, exit_code: int = -1) -> None:
        """Restart the orchestrator and re-submit all pending work.

        Raises OrchestratorCrashError once ``max_restarts`` is exceeded.
        """
        self._restart_count += 1
        self._crash_exit_codes.append(exit_code)

        crash_log_path = get_log_file_path().parent / ".orchestrator-crash.log"
        pending_mutants = list(self._pending)
        self._logger.error(
            f"Orchestrator crashed with exit code {exit_code}. "
            f"Check {crash_log_path} and {get_log_file_path()} for details."
        )
        self._logger.error(f"Pending mutants at time of crash ({len(pending_mutants)}): {pending_mutants}")

        if self._restart_count > self.max_restarts:
            raise OrchestratorCrashError(
                exit_code=-1,
                lost_mutants=list(self._pending),
                crash_log=str(crash_log_path) if crash_log_path.exists() else None,
            )

        lost_count = len(self._pending)
        self._logger.warning(
            f"Orchestrator crashed, restarting (attempt {self._restart_count}/{self.max_restarts}), "
            f"re-submitting {lost_count} pending mutant(s)"
        )

        pending_work_copy = dict(self._pending_work)

        self._start_orchestrator()

        if self.work_pipe_write is None:
            raise RuntimeError("Failed to restart orchestrator - work pipe not created")
        for mutant_name, (tests, cpu_time_limit, estimated_time, _) in pending_work_copy.items():
            send_message(self.work_pipe_write, (mutant_name, list(tests), cpu_time_limit))
            self._pending_work[mutant_name] = (tests, cpu_time_limit, estimated_time, datetime.now())
            self._logger.debug(f"Re-submitted {mutant_name} to new orchestrator")

        self._logger.info(f"Orchestrator restarted, {lost_count} mutant(s) re-submitted")

    def _write_crash_log(self, exception: Exception) -> None:
        """Best-effort dump of orchestrator crash info for debugging."""
        crash_file = get_log_file_path().parent / ".orchestrator-crash.log"
        try:
            crash_file.parent.mkdir(parents=True, exist_ok=True)
            with open(crash_file, "w") as f:
                f.write(f"Orchestrator crash at {datetime.now()}\n")
                f.write(f"Exception: {exception}\n")
                f.write(traceback.format_exc())
        except Exception:
            pass

    def _setup_sigchld_pipe(self) -> tuple[int, int]:
        """Set up a self-pipe so SIGCHLD wakes the orchestrator's select()."""
        sigchld_pipe_r, sigchld_pipe_w = os.pipe()
        os.set_blocking(sigchld_pipe_r, False)
        os.set_blocking(sigchld_pipe_w, False)

        def sigchld_handler(signum: int, frame: Any) -> None:
            # Write a byte to wake up select(); ignore a full pipe.
            try:
                os.write(sigchld_pipe_w, b"c")
            except (BlockingIOError, OSError):
                pass

        signal.signal(signal.SIGCHLD, sigchld_handler)
        return sigchld_pipe_r, sigchld_pipe_w

    def _wait_for_child_event(self, sigchld_pipe_r: int, timeout: float | None) -> bool:
        """Block until a child exits (SIGCHLD) or the timeout elapses.

        Returns True if a child may be ready to reap, False on timeout.
        """
        try:
            readable, _, _ = select.select([sigchld_pipe_r], [], [], timeout)
            if readable:
                try:
                    while os.read(sigchld_pipe_r, 1024):
                        pass
                except BlockingIOError:
                    pass  # Expected once the pipe is drained.
                return True
            return False
        except InterruptedError:
            return True  # Interrupted by a signal; check anyway.

    def _orchestrator_main(self, work_fd: int, result_fd: int) -> None:
        """Orchestrator: import pytest once, then fork a grandchild per mutant."""
        # The parent owns shutdown, so ignore SIGINT here.
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        if config().log_to_file or config().debug:
            setup_file_logging()
        orchestrator_logger = get_logger("mutmut.hotfork.orchestrator")
        orchestrator_logger.info(f"Hot-fork orchestrator starting (pid={os.getpid()})")

        test_runner: TestRunner = self.test_runner_class(**self.test_runner_args)

        # Warm up with stdout/stderr suppressed so collection output does not
        # corrupt the interactive terminal.
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = open(os.devnull, "w")
        try:
            test_runner.warm_up()
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
        orchestrator_logger.info("Test runner initialized, ready for work")

        # Set up the SIGCHLD pipe AFTER warm_up: libraries like gevent may
        # monkey-patch signals during import/collection.
        sigchld_pipe_r, sigchld_pipe_w = self._setup_sigchld_pipe()
        orchestrator_logger.debug("SIGCHLD notification pipe set up")

        running: dict[int, HotForkRunner.RunningChild] = {}

        def terminate(signum: int, frame: Any) -> None:
            # The parent SIGTERMs us on Ctrl-C. Take the grandchildren down too,
            # otherwise they are reparented to init and keep burning CPU until
            # their RLIMIT_CPU fires.
            for child_pid in list(running):
                try:
                    os.kill(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            os._exit(0)

        signal.signal(signal.SIGTERM, terminate)

        while True:
            self._reap_children(running, result_fd, orchestrator_logger, sigchld_pipe_r, block=False)

            while len(running) >= self.max_workers:
                self._reap_children(running, result_fd, orchestrator_logger, sigchld_pipe_r, block=True, timeout=1.0)

            readable, _, _ = select.select([work_fd, sigchld_pipe_r], [], [], 1.0)

            if sigchld_pipe_r in readable:
                self._reap_children(running, result_fd, orchestrator_logger, sigchld_pipe_r, block=False)

            if work_fd not in readable:
                continue

            try:
                msg = recv_message(work_fd)
            except EOFError:
                break

            if msg is None:
                break

            mutant_name, tests, cpu_time_limit = msg

            # Wall-clock timeout is shorter than the CPU limit: multi-threaded
            # code can burn N*wall CPU seconds across N cores, so half the CPU
            # limit is a reasonable wall bound.
            wall_timeout = cpu_time_limit / 2
            orchestrator_logger.debug(
                f"Received mutant: {mutant_name} ({len(tests)} tests, "
                f"cpu_limit={cpu_time_limit}s, wall_timeout={wall_timeout}s)"
            )

            child_pid = os.fork()
            if child_pid == 0:
                # Grandchild: run this mutant's tests under a CPU limit.
                worker_logger = get_logger(f"mutmut.hotfork.worker.{os.getpid()}")
                worker_logger.debug(f"Starting {mutant_name} ({len(tests)} tests)")

                sys.stdout = sys.stderr = open(os.devnull, "w")

                limit = cpu_time_limit + int(process_time())
                resource.setrlimit(resource.RLIMIT_CPU, (limit, limit + 1))

                set_mutant_under_test(mutant_name)
                try:
                    exit_code = test_runner.run_tests(mutant_name=mutant_name, tests=tests)
                except Exception:
                    exit_code = -1

                worker_logger.debug(f"Finished {mutant_name}: exit={exit_code}")
                os._exit(exit_code)

            running[child_pid] = self.RunningChild(mutant_name, time.time(), wall_timeout)
            # A background thread sends SIGXCPU when the wall timeout expires.
            register_timeout(child_pid, wall_timeout)

        orchestrator_logger.info("Work queue exhausted, waiting for remaining children")
        while running:
            self._reap_children(running, result_fd, orchestrator_logger, sigchld_pipe_r, block=True, timeout=1.0)

        try:
            os.close(sigchld_pipe_r)
            os.close(sigchld_pipe_w)
        except OSError:
            pass
        orchestrator_logger.info("Orchestrator shutting down cleanly")

    def _reap_children(
        self,
        running: dict[int, RunningChild],
        result_fd: int,
        orchestrator_logger: logging.Logger,
        sigchld_pipe_r: int,
        block: bool,
        timeout: float | None = None,
    ) -> None:
        """Reap completed grandchildren and stream their results to the parent."""
        if block:
            if not self._wait_for_child_event(sigchld_pipe_r, timeout):
                return  # Timeout reached, no child ready.

        # Reap ALL ready children in a loop: the kernel coalesces SIGCHLD, so a
        # single signal can cover several exits. Reaping only one per signal
        # would leave children unreaped and could hang select() forever.
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return  # No children.
            if pid == 0:
                return  # No more children ready.

            # Unknown pids (coverage helpers, pytest plugins, ...) are ignored.
            if pid not in running:
                continue

            child = running.pop(pid)
            exit_code = os.waitstatus_to_exitcode(status)
            duration = time.time() - child.start_time
            orchestrator_logger.debug(f"Completed {child.mutant_name}: exit={exit_code} ({duration:.3f}s)")
            send_message(result_fd, (child.mutant_name, exit_code))

    def submit(self, mutant_name: str, tests: list[str], cpu_time_limit: int, estimated_time: float) -> None:
        if not tests:
            # Matches ForkRunner: nothing to run, so resolve it here as "no tests"
            # rather than paying for a round trip through the orchestrator.
            self._no_tests_results.append(MutantResult(mutant_name=mutant_name, exit_code=33, duration=0.0))
            return

        if self.work_pipe_write is None:
            raise RuntimeError("HotForkRunner not started - call startup() first")
        send_message(self.work_pipe_write, (mutant_name, list(tests), cpu_time_limit))
        self._pending.add(mutant_name)
        self._pending_work[mutant_name] = (list(tests), cpu_time_limit, estimated_time, datetime.now())

    def has_capacity(self) -> bool:
        return len(self._pending) < self.max_workers

    def signal_work_complete(self) -> None:
        """Close the work pipe so the orchestrator sees EOF and drains workers."""
        if self.work_pipe_write is None:
            return
        try:
            os.close(self.work_pipe_write)
        except OSError:
            pass
        finally:
            self.work_pipe_write = None
        self._logger.debug("Work pipe closed, orchestrator will drain remaining workers")

    def _check_orchestrator_alive(self) -> None:
        """Detect an orchestrator crash and restart it, re-submitting pending work.

        A clean exit (code 0) is left alone. Raises OrchestratorCrashError once
        the restart budget is exhausted.
        """
        if self.orchestrator_pid is None:
            return
        try:
            pid, status = os.waitpid(self.orchestrator_pid, os.WNOHANG)
            if pid == self.orchestrator_pid:
                exit_code = os.waitstatus_to_exitcode(status)
                self.orchestrator_pid = None

                if exit_code == 0:
                    self._logger.debug(f"Orchestrator (pid={pid}) exited cleanly")
                    return

                self._logger.warning(f"Orchestrator (pid={pid}) crashed with exit code {exit_code}")
                self._restart_orchestrator_with_pending_work(exit_code=exit_code)
        except ChildProcessError:
            self._logger.warning("Orchestrator process not found")
            self.orchestrator_pid = None
            self._restart_orchestrator_with_pending_work(exit_code=-1)

    def wait_for_result(self, timeout: float | None = None) -> MutantResult:
        if self._no_tests_results:
            return self._no_tests_results.pop(0)
        if self.result_pipe_read is None:
            raise RuntimeError("HotForkRunner not started - call startup() first")
        while True:
            self._check_orchestrator_alive()

            r, _, _ = select.select([self.result_pipe_read], [], [], timeout or 1.0)
            if not r:
                if timeout is not None:
                    raise Empty()
                continue

            try:
                mutant_name, exit_code = recv_message(self.result_pipe_read)
            except EOFError as err:
                self._check_orchestrator_alive()
                raise OrchestratorCrashError(exit_code=-1, lost_mutants=list(self._pending), crash_log=None) from err

            self._pending.discard(mutant_name)
            self._pending_work.pop(mutant_name, None)

            return MutantResult(mutant_name=mutant_name, exit_code=exit_code, duration=0.0)

    def pending_count(self) -> int:
        # Queued no-test results are submitted work nobody has collected yet.
        return len(self._pending) + len(self._no_tests_results)

    def stop_all_workers(self) -> None:
        if self.orchestrator_pid:
            try:
                os.kill(self.orchestrator_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def shutdown(self) -> None:
        """Close the work pipe, drain remaining results, and reap the orchestrator."""
        if self._shutting_down:
            return
        self._shutting_down = True

        self._logger.info("HotForkRunner shutting down")

        self.signal_work_complete()

        # Drain any results still in flight so completed work is captured.
        while self._pending:
            try:
                result = self.wait_for_result(timeout=1.0)
                self._pending.discard(result.mutant_name)
                self._pending_work.pop(result.mutant_name, None)
            except (Empty, OrchestratorCrashError):
                break

        if self.orchestrator_pid:
            try:
                os.waitpid(self.orchestrator_pid, 0)
            except ChildProcessError:
                pass

        if self.result_pipe_read is not None:
            try:
                os.close(self.result_pipe_read)
            except OSError:
                pass

        gc.unfreeze()
        self._logger.info("HotForkRunner shutdown complete")

    def collect_stats(self, tests: Iterable[str] | None) -> int:
        """Collect stats in a forked child so the parent never imports pytest.

        The child runs stats and packs the collected mapping into a StatsResult,
        which the parent merges back into ``state()``.
        """
        tests_list = list(tests) if tests is not None else None

        def _run_stats() -> dict[str, Any]:
            child_runner: TestRunner = self.test_runner_class(**self.test_runner_args)
            exit_code = child_runner.run_stats(tests=tests_list or [])
            return StatsResult(
                exit_code=exit_code,
                tests_by_mangled_function_name=dict(state().tests_by_mangled_function_name),
                duration_by_test=dict(state().duration_by_test),
                stats_time=state().stats_time or 0.0,
                function_dependencies=dict(state().function_dependencies),
            ).to_dict()

        result = StatsResult.from_dict(run_in_fork_with_result(_run_stats))

        for k, v in result.tests_by_mangled_function_name.items():
            state().tests_by_mangled_function_name[k] |= v
        state().duration_by_test.update(result.duration_by_test)
        state().stats_time = result.stats_time
        for k, v in result.function_dependencies.items():
            state().function_dependencies[k] = v

        return result.exit_code

    def run_clean_tests(self, tests: Iterable[str]) -> int:
        tests_list = list(tests)

        def _run_tests() -> int:
            child_runner: TestRunner = self.test_runner_class(**self.test_runner_args)
            return child_runner.run_tests(mutant_name=None, tests=tests_list)

        return run_in_fork(_run_tests)

    def run_forced_fail(self) -> int:
        def _run_forced_fail() -> int:
            child_runner: TestRunner = self.test_runner_class(**self.test_runner_args)
            return child_runner.run_forced_fail()

        return run_in_fork(_run_forced_fail)

    def list_all_tests(self) -> ListAllTestsResult:
        def _list_all_tests() -> dict[str, Any]:
            child_runner: TestRunner = self.test_runner_class(**self.test_runner_args)
            result = child_runner.list_all_tests()
            return {"ids": list(result.ids)}

        data = run_in_fork_with_result(_list_all_tests)
        return ListAllTestsResult(ids=set(data["ids"]))


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
        return HotForkRunner(
            max_workers=max_workers,
            test_runner_class=PytestRunner,
            test_runner_args={},
            debug=config().debug,
            max_restarts=config().max_orchestrator_restarts,
        )

    pytest_runner = PytestRunner()
    pytest_runner.prepare_main_test_run()
    return ForkRunner(max_workers=max_workers, test_runner=pytest_runner, debug=config().debug)
