orig_print = print


def print(x='', **kwargs):
    x = x.decode("utf-8")
    orig_print(x.encode("utf-8"), **kwargs)


class TimeoutError(OSError):
    """Defining TimeoutError for Python 2 compatibility"""


TimeoutError = TimeoutError