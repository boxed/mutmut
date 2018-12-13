#!/usr/bin/python
# -*- coding: utf-8 -*-

"""pytests for :mod:`mutmut.runner`"""

from datetime import datetime

import pytest

from mutmut.runner import popen_streaming_output


def test_timeout():
    start = datetime.now()

    with pytest.raises(TimeoutError):
        popen_streaming_output('python -c "import time; time.sleep(4)"',
                               lambda line: line, timeout=0.1)

    assert (datetime.now() - start).total_seconds() < 3


def test_timeout_non_timeout():
    start = datetime.now()

    popen_streaming_output('python -c "import time; time.sleep(4)"',
                           lambda line: line, timeout=20)

    assert (datetime.now() - start).total_seconds() >= 4
    assert (datetime.now() - start).total_seconds() < 10
