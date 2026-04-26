"""
Terminal display utilities for mutmut.

This module contains utilities for displaying status information in the terminal,
including a spinner and rate-limited status printer.
"""

import itertools
import sys
from datetime import datetime
from datetime import timedelta
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
