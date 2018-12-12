#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Terminal printing utilities"""

import itertools
import sys

spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')


def status_printer():
    """Manage the printing and in-place updating of a line of characters.

    .. note::

        if the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]

    def p(s):
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        if sys.version_info < (3, 0):  # pragma: no cover (python 2 specific)
            output = output.encode('utf8')
        sys.stdout.write(output)
        sys.stdout.flush()
        last_len[0] = len_s

    return p


print_status = status_printer()
