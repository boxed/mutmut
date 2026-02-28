"""Tests for safe_setproctitle module.

This test verifies that setproctitle crashes on macOS Python 3.14+ after fork
when CoreFoundation has been loaded (which happens during normal mutmut operation).
When setproctitle is fixed upstream, this test will fail and we can remove the workaround.
"""

import os
import platform
import signal
import sys

import pytest
from setproctitle import setproctitle

from mutmut.utils.safe_setproctitle import safe_setproctitle

# Only run this test on macOS with Python 3.14+
IS_MACOS_314 = sys.version_info >= (3, 14) and platform.system() == "Darwin"


@pytest.mark.skipif(not IS_MACOS_314, reason="setproctitle only crashes after fork on macOS Python 3.14+")
def test_setproctitle_crashes_after_fork_with_corefoundation_loaded():
    """Verify setproctitle segfaults after fork when CoreFoundation is loaded.

    This test exists to detect when setproctitle is fixed upstream.
    If this test FAILS, it means setproctitle no longer crashes and we can
    remove the workaround in safe_setproctitle.py.

    The crash only happens when CoreFoundation has been loaded before fork.
    We trigger this by calling setproctitle once in the parent before forking.
    """
    # Import and call setproctitle in the parent first - this loads CoreFoundation

    setproctitle("parent process")

    pid = os.fork()

    if pid == 0:
        # Child process - call setproctitle again
        try:
            setproctitle("child process")
            # If we get here, setproctitle didn't crash - exit with success
            os._exit(0)
        except Exception:
            # If it raises a Python exception instead of segfaulting
            os._exit(1)
    else:
        # Parent process - wait for child and check exit status
        _, status = os.waitpid(pid, 0)

        if os.WIFSIGNALED(status):
            exit_signal = os.WTERMSIG(status)
            assert exit_signal == signal.SIGSEGV, (
                f"Expected SIGSEGV (11), got signal {exit_signal}. setproctitle crash behavior may have changed."
            )
        else:
            exit_code = os.WEXITSTATUS(status)
            pytest.fail(
                f"setproctitle did NOT crash (exit code {exit_code}). "
                "The library may have been fixed! Consider removing the "
                "workaround in safe_setproctitle.py"
            )


@pytest.mark.skipif(not IS_MACOS_314, reason="safe_setproctitle workaround only applies to macOS Python 3.14+")
def test_safe_setproctitle_does_not_crash_after_fork():
    """Verify our safe_setproctitle wrapper doesn't crash after fork."""
    pid = os.fork()

    if pid == 0:
        # Child process - use our safe wrapper
        try:
            safe_setproctitle("test title")
            os._exit(0)  # Success
        except Exception:
            os._exit(1)  # Failed with exception
    else:
        # Parent process
        _, status = os.waitpid(pid, 0)

        if os.WIFSIGNALED(status):
            exit_signal = os.WTERMSIG(status)
            pytest.fail(f"safe_setproctitle crashed with signal {exit_signal}! The workaround is not working.")
        else:
            exit_code = os.WEXITSTATUS(status)
            assert exit_code == 0, f"safe_setproctitle failed with exit code {exit_code}"
