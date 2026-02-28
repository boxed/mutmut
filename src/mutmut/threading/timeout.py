import heapq
import os
import signal
import time
from threading import Condition
from threading import Thread

_timeout_heap: list[tuple[float, int]] = []  # (timeout_timestamp, pid)
_heap_lock = Condition()
_checker_started = False


def register_timeout(pid: int, timeout_s: float) -> None:
    """Register a timeout for a given PID.

    Starts the timeout checker thread if not already started.

    On timeout sends SIGXCPU to the process.

    Args:
        pid: The process ID to register the timeout for.
        timeout_s: The number of seconds until the timeout occurs.
    """
    global _checker_started
    if not _checker_started:
        _checker_started = True
        Thread(target=_timeout_checker_thread, name=f"{os.getpid()}-mutmut-timeout-checker", daemon=True).start()

    deadline = time.time() + timeout_s
    with _heap_lock:
        heapq.heappush(_timeout_heap, (deadline, pid))
        _heap_lock.notify()


def _timeout_checker_thread() -> None:
    """Thread function that checks for timeouts and terminates processes.

    We make a trade-off here in the name of simplicity by not exposing a
    mechanism to cancel timeouts, which saves us an O(n) operation on each
    timeout we would cancel. Instead, we let expired entries for already-terminated
    processes remain in the heap until they reach the top and are popped off.
    The downside is a bit of memory bloat but each tuple is ~72 bytes so
    even with 10,000 backed up timeouts it's less than 1MB.
    """
    while True:
        with _heap_lock:
            while not _timeout_heap:
                _heap_lock.wait()
            now = time.time()
            while _timeout_heap and _timeout_heap[0][0] <= now:
                _, pid = heapq.heappop(_timeout_heap)
                try:
                    os.kill(pid, signal.SIGXCPU)
                except ProcessLookupError:
                    pass  # Process already terminated
        time.sleep(1)
