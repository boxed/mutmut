from time import time
from unittest.mock import MagicMock, call

import pytest

from mutmut.runner import Config, compute_exit_code, popen_streaming_output
from mutmut.utils import TimeoutError


def test_compute_return_code():
    # mock of Config for ease of testing
    class MockConfig(Config):
        def __init__(self, killed_mutants, surviving_mutants,
                     surviving_mutants_timeout, suspicious_mutants):
            self.killed_mutants = killed_mutants
            self.surviving_mutants = surviving_mutants
            self.surviving_mutants_timeout = surviving_mutants_timeout
            self.suspicious_mutants = suspicious_mutants

    assert compute_exit_code(MockConfig(0, 0, 0, 0)) == 0
    assert compute_exit_code(MockConfig(0, 0, 0, 1)) == 8
    assert compute_exit_code(MockConfig(0, 0, 1, 0)) == 4
    assert compute_exit_code(MockConfig(0, 0, 1, 1)) == 12
    assert compute_exit_code(MockConfig(0, 1, 0, 0)) == 2
    assert compute_exit_code(MockConfig(0, 1, 0, 1)) == 10
    assert compute_exit_code(MockConfig(0, 1, 1, 0)) == 6
    assert compute_exit_code(MockConfig(0, 1, 1, 1)) == 14

    assert compute_exit_code(MockConfig(1, 0, 0, 0)) == 0
    assert compute_exit_code(MockConfig(1, 0, 0, 1)) == 8
    assert compute_exit_code(MockConfig(1, 0, 1, 0)) == 4
    assert compute_exit_code(MockConfig(1, 0, 1, 1)) == 12
    assert compute_exit_code(MockConfig(1, 1, 0, 0)) == 2
    assert compute_exit_code(MockConfig(1, 1, 0, 1)) == 10
    assert compute_exit_code(MockConfig(1, 1, 1, 0)) == 6
    assert compute_exit_code(MockConfig(1, 1, 1, 1)) == 14

    assert compute_exit_code(MockConfig(0, 0, 0, 0), Exception()) == 1
    assert compute_exit_code(MockConfig(0, 0, 0, 1), Exception()) == 9
    assert compute_exit_code(MockConfig(0, 0, 1, 0), Exception()) == 5
    assert compute_exit_code(MockConfig(0, 0, 1, 1), Exception()) == 13
    assert compute_exit_code(MockConfig(0, 1, 0, 0), Exception()) == 3
    assert compute_exit_code(MockConfig(0, 1, 0, 1), Exception()) == 11
    assert compute_exit_code(MockConfig(0, 1, 1, 0), Exception()) == 7
    assert compute_exit_code(MockConfig(0, 1, 1, 1), Exception()) == 15

    assert compute_exit_code(MockConfig(1, 0, 0, 0), Exception()) == 1
    assert compute_exit_code(MockConfig(1, 0, 0, 1), Exception()) == 9
    assert compute_exit_code(MockConfig(1, 0, 1, 0), Exception()) == 5
    assert compute_exit_code(MockConfig(1, 0, 1, 1), Exception()) == 13
    assert compute_exit_code(MockConfig(1, 1, 0, 0), Exception()) == 3
    assert compute_exit_code(MockConfig(1, 1, 0, 1), Exception()) == 11
    assert compute_exit_code(MockConfig(1, 1, 1, 0), Exception()) == 7
    assert compute_exit_code(MockConfig(1, 1, 1, 1), Exception()) == 15


def test_popen_streaming_output_timeout():
    start = time()
    with pytest.raises(TimeoutError):
        popen_streaming_output('python -c "import time; time.sleep(4)"',
                               lambda line: line, timeout=0.1)

    assert (time() - start) < 3


def test_popen_streaming_output_stream():
    mock = MagicMock()
    popen_streaming_output(
        'python -c "print(\'first\'); print(\'second\')"',
        callback=mock
    )
    mock.assert_has_calls([call('first'), call('second')])

    mock = MagicMock()
    popen_streaming_output(
        'python -c "import time; print(\'first\'); time.sleep(1); print(\'second\'); print(\'third\')"',
        callback=mock
    )
    mock.assert_has_calls([call('first'), call('second'), call('third')])

    mock = MagicMock()
    popen_streaming_output('python -c "exit(0);"', callback=mock)
    mock.assert_not_called()
