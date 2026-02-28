"""
Fork isolation utilities for keeping the parent process clean.

The main process must not import pytest/test code directly, because test
conftest.py files may call gevent.monkey.patch_all() or import grpc, which
makes the process fork-unsafe.

These utilities run operations in forked children so the parent stays clean.
Uses pipe-based IPC for reduced overhead (no temp files, no cleanup needed).
"""

import os
import pickle
from collections.abc import Callable
from typing import Any


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
