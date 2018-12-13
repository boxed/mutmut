#!/usr/bin/python
# -*- coding: utf-8 -*-

"""pytests for :mod:`mutmut.runner`"""

import subprocess
from datetime import datetime

import pytest

from mutmut.runner import popen_streaming_output
from tests.test_main import in_travis


@pytest.mark.skipif(in_travis, reason='This test does not work on TravisCI')
def test_timeout():
    start = datetime.now()

    with pytest.raises(subprocess.TimeoutExpired):
        popen_streaming_output('python -c "import time; time.sleep(4)"',
                               lambda line: line, timeout=0.1)

    assert (datetime.now() - start).total_seconds() < 3
