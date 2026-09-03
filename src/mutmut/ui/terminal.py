import itertools
import sys
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta

spinner = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


def status_printer() -> Callable[..., None]:
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
        assert sys.__stdout__ is not None
        sys.__stdout__.write(output)
        sys.__stdout__.flush()
        last_len[0] = len_s

    return p


print_status = status_printer()
