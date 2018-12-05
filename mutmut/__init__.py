# coding=utf-8

import sys

__version__ = '1.0.1'

ALL = ('all', -1)


if sys.version_info < (3, 0):   # pragma: no cover (python 2 specific)
    # noinspection PyUnresolvedReferences
    text_types = (str, unicode)
else:
    text_types = (str,)

