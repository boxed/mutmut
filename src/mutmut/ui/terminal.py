"""
Terminal display utilities for mutmut.

This module contains utilities for displaying status information in the terminal,
including a spinner, rate-limited status printer, output capturing, and timed tasks.
"""

import itertools
import sys
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from io import TextIOBase
from typing import Protocol

spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


class PrintStatusFn(Protocol):
    """Protocol for status printing functions."""

    def __call__(self, s: str, *, force_output: bool = False) -> None: ...


def status_printer() -> PrintStatusFn:
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]
    last_update = [datetime(1900, 1, 1)]
    update_threshold = timedelta(seconds=0.1)

    def p(s: str, *, force_output: bool = False) -> None:
        if not force_output and (datetime.now() - last_update[0]) < update_threshold:
            return
        s = next(spinner) + " " + s
        len_s = len(s)
        output = "\r" + s + (" " * max(last_len[0] - len_s, 0))
        sys.__stdout__.write(output)  # type: ignore [union-attr]
        sys.__stdout__.flush()  # type: ignore [union-attr]
        last_len[0] = len_s

    return p


print_status = status_printer()


def format_duration(seconds: float) -> str:
    """Format a duration in human-readable form.

    - Under 10 seconds: milliseconds (e.g., "1234ms")
    - Under 10 minutes: seconds with decimal (e.g., "45.2s")
    - Under 1 hour: minutes and seconds (e.g., "12m30s")
    - 1 hour or more: hours, minutes and seconds (e.g., "1h15m45s")
    """
    if seconds < 10:
        return f"{round(seconds * 1000)}ms"
    elif seconds < 600:  # 10 minutes
        return f"{seconds:.1f}s"
    elif seconds < 3600:  # 1 hour
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m{secs}s"
    else:
        hours = int(seconds // 3600)
        remaining = seconds % 3600
        minutes = int(remaining // 60)
        secs = int(remaining % 60)
        return f"{hours}h{minutes}m{secs}s"


class CatchOutput:
    """Context manager to capture stdout/stderr while showing a spinner.

    Usage:
        with CatchOutput(spinner_title='Running tests') as catcher:
            exit_code = run_tests()
            if exit_code != 0:
                catcher.dump_output()
    """

    def __init__(
        self,
        callback: Callable[[str], None] = lambda s: None,
        spinner_title: str | None = None,
        debug: bool = False,
    ) -> None:
        self.strings: list[str] = []
        self.spinner_title = spinner_title or ""
        self.debug = debug
        if debug:
            self.spinner_title += "\n"

        class StdOutRedirect(TextIOBase):
            def __init__(self, catcher: "CatchOutput") -> None:
                self.catcher = catcher

            def write(self, s: str) -> int:
                callback(s)
                if spinner_title:
                    print_status(spinner_title)
                self.catcher.strings.append(s)
                return len(s)

        self.redirect = StdOutRedirect(self)

    def stop(self) -> None:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    def start(self) -> None:
        if self.spinner_title:
            print_status(self.spinner_title)
        sys.stdout = self.redirect
        sys.stderr = self.redirect
        if self.debug:
            self.stop()

    def dump_output(self) -> None:
        self.stop()
        print()
        for line in self.strings:
            print(line, end="")

    def __enter__(self) -> "CatchOutput":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.stop()
        if self.spinner_title:
            print()


class SpinnerTask:
    """Context manager for timed operations with spinner output.

    Automatically handles timing and prints "done in Xms" when the context exits.
    Supports both isolated mode (direct print_status) and captured mode (CatchOutput).

    Usage:
        with SpinnerTask('Running stats', isolated=True):
            do_work()

        # Or capture output:
        with SpinnerTask('Running tests') as task:
            result = do_work()
            if error:
                task.dump_output()

        # Access elapsed time after context exits:
        with SpinnerTask('Running tests') as task:
            do_work()
        elapsed_seconds = task.elapsed_seconds
    """

    def __init__(self, title: str, isolated: bool = False, debug: bool = False) -> None:
        self.title = title + (" (isolated)" if isolated else "")
        self.isolated = isolated
        self.debug = debug
        self.start_time: datetime | None = None
        self.elapsed_seconds: float = 0.0
        self._catch_output: CatchOutput | None = None

    def __enter__(self) -> "SpinnerTask":
        self.start_time = datetime.now()
        if self.isolated:
            print_status(self.title)
        else:
            self._catch_output = CatchOutput(spinner_title=self.title, debug=self.debug)
            self._catch_output.__enter__()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self.start_time is None:
            return
        elapsed = datetime.now() - self.start_time
        self.elapsed_seconds = elapsed.total_seconds()
        if self.isolated:
            print(f"\n    done in {format_duration(self.elapsed_seconds)}")
        else:
            if self._catch_output:
                self._catch_output.__exit__(exc_type, exc_val, exc_tb)
            print(f"    done in {format_duration(self.elapsed_seconds)}")

    def dump_output(self) -> None:
        """Dump captured output (for error handling)."""
        if self._catch_output:
            self._catch_output.dump_output()
