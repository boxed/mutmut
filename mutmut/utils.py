from __future__ import print_function

import sys

if sys.version_info < (3, 0):  # pragma: no cover (python 2 specific)
    orig_print = print

    # This little hack is needed to get the click tester working on python 2.7
    def print(x='', **kwargs):
        x = x.decode("utf-8")
        orig_print(x.encode("utf-8"), **kwargs)


    class TimeoutError(OSError):
        """Defining TimeoutError for Python 2 compatibility"""
else:
    TimeoutError = TimeoutError
    print = print
