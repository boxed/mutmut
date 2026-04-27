import os
import signal
import threading
import time
from unittest.mock import patch

import pytest

from mutmut.workers import timeout


@pytest.fixture(autouse=True)
def clear_heap():
    timeout._timeout_heap.clear()
    yield
    timeout._timeout_heap.clear()


class TestRegisterTimeout:
    """Tests for register_timeout function."""

    def test_adds_entry_to_heap(self) -> None:
        """Verify that registering a timeout adds an entry to the heap."""
        assert len(timeout._timeout_heap) == 0

        timeout.register_timeout(pid=99999999, timeout_s=60)

        assert len(timeout._timeout_heap) == 1
        deadline, pid = timeout._timeout_heap.pop()
        assert pid == 99999999
        assert deadline > time.time()  # Deadline should be in the future
        # this is redundant but it makes sure that we won't try and reap a random process
        assert len(timeout._timeout_heap) == 0

    def test_deadline_calculation(self) -> None:
        """Verify deadline is calculated as now + timeout_seconds."""
        before = time.time()
        timeout.register_timeout(pid=99999, timeout_s=0.5)
        after = time.time()

        deadline, pid = timeout._timeout_heap[0]
        assert pid == 99999
        assert before + 0.5 <= deadline <= after + 0.5

    def test_heap_ordering(self) -> None:
        """Verify heap maintains min-heap property (earliest deadline first)."""
        # Add in reverse order
        timeout.register_timeout(pid=3, timeout_s=80.0)
        timeout.register_timeout(pid=1, timeout_s=60.0)
        timeout.register_timeout(pid=2, timeout_s=70.0)

        # Heap root should be earliest deadline (pid=1)
        _, root_pid = timeout._timeout_heap[0]
        assert root_pid == 1


class TestTimeoutCheckerThread:
    """Tests for the timeout checker thread behavior."""

    def test_kills_process_after_deadline(self) -> None:
        """Verify that a process receives SIGXCPU after its deadline."""
        # Fork a child that just sleeps
        pid = os.fork()
        if pid == 0:
            # Child: sleep forever
            time.sleep(60)
            os._exit(0)

        try:
            # Register a short timeout (this also starts the checker)
            timeout.register_timeout(pid=pid, timeout_s=0.1)

            # depending on the test runner (looking at you vscode)
            # the actual amount of time it takes for everything to
            # start/timeout can vary, to avoid waiting longer than
            # we need to just poll for termination up to 5s
            terminated = False
            for _ in range(50):  # 50 * 0.1s = 5 seconds max
                result_pid, _ = os.waitpid(pid, os.WNOHANG)
                if result_pid == pid:
                    terminated = True
                    break
                time.sleep(0.1)

            assert terminated, "Child process should have been terminated"
        finally:
            # Cleanup: ensure child is dead
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass

    def test_handles_already_terminated_process(self) -> None:
        """Verify no error when process exits before timeout fires."""
        # Fork a child that exits immediately
        pid = os.fork()
        if pid == 0:
            os._exit(0)

        # Wait for child to exit
        os.waitpid(pid, 0)

        # Register timeout for already-dead process - should not raise
        timeout.register_timeout(pid=pid, timeout_s=0.1)

        # Wait for timeout to fire
        time.sleep(0.5)
        # No exception means success

    def test_processes_multiple_timeouts_in_order(self) -> None:
        """Verify multiple timeouts are processed in deadline order.

        We use a relaly long max time for this test because of inconsistent
        runtimes in the docker test containers. The most important aspect of
        is the order of the reaping as opposed to the precision when when it
        reaps
        """

        # Create multiple sleeping children
        pids = []
        for _ in range(3):
            pid = os.fork()
            if pid == 0:
                time.sleep(60)
                os._exit(0)
            pids.append(pid)

        try:
            # Register with different timeouts (reversed order)
            timeout.register_timeout(pid=pids[2], timeout_s=0.3)
            timeout.register_timeout(pid=pids[0], timeout_s=0.1)
            timeout.register_timeout(pid=pids[1], timeout_s=0.2)
            result_pid = None
            # All children should be terminated
            for pid in pids:
                for _ in range(50):  # 3 * 50 * 0.1s = 15 seconds max
                    result_pid, _ = os.waitpid(pid, os.WNOHANG)
                    if result_pid == pid:
                        break
                    time.sleep(0.1)
                assert result_pid == pid, f"Process {pid} should have been terminated"
        finally:
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
                except (ProcessLookupError, ChildProcessError):
                    pass


class TestLazyStart:
    """Tests for lazy-start behavior of the timeout checker."""

    def test_checker_starts_on_first_registration(self) -> None:
        """Verify the checker thread starts automatically on first register_timeout call."""
        timeout._checker_started = False

        timeout.register_timeout(pid=12345, timeout_s=60.0)
        assert timeout._checker_started is True

    def test_multiple_registrations_dont_start_multiple_threads(self) -> None:
        """Verify multiple register_timeout calls don't spawn multiple threads."""
        timeout._checker_started = False
        pid = 999999  # Dummy PID for naming
        with patch.object(timeout.os, "getpid", return_value=pid):
            timeout.register_timeout(pid=1, timeout_s=60.0)
            timeout.register_timeout(pid=2, timeout_s=60.0)
            timeout.register_timeout(pid=3, timeout_s=60.0)

        # Count timeout checker threads
        checker_threads = [t for t in threading.enumerate() if f"{pid}-mutmut-timeout-checker" in t.name]
        assert len(checker_threads) == 1
