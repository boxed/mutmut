# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import time
import xml.etree.ElementTree as ET

import pytest

from coverage import CoverageData

from click.testing import CliRunner

from mutmut.__main__ import main, python_source_files, popen_streaming_output, \
    CompatTimeoutError, read_coverage_data

try:
    from unittest.mock import MagicMock, call
except ImportError:
    from mock import MagicMock, call


file_to_mutate_lines = [
    "def foo(a, b):",
    "    return a < b",
    "e = 1",
    "f = 3",
    "d = dict(e=f)",
]

if sys.version_info >= (3, 6):   # pragma: no cover (python 2 specific)
    file_to_mutate_lines.append("g: int = 2")
    EXPECTED_MUTANTS = 8
else:
    # python2 is given a more primitive mutation base
    # thus can obtain 1 more mutant
    file_to_mutate_lines.append("g = 2")
    EXPECTED_MUTANTS = 9


file_to_mutate_contents = '\n'.join(file_to_mutate_lines) + '\n'

test_file_contents = '''
from foo import *

def test_foo():
   assert foo(1, 2) is True
   assert foo(2, 2) is False
   
   assert e == 1
   assert f == 3
   assert d == dict(e=f)
   assert g == 2
'''


@pytest.fixture
def filesystem(tmpdir_factory):
    test_fs = tmpdir_factory.mktemp("test_fs")
    test_fs.join("foo.py").write(file_to_mutate_contents)
    os.mkdir(str(test_fs.join("tests")))
    test_fs.join("tests", "test_foo.py").write(test_file_contents)
    os.chdir(str(test_fs))
    yield test_fs

    # This is a hack to get pony to forget about the old db file
    # otherwise Pony thinks we've already created the tables
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


def test_simple_apply(filesystem):
    result = CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    CliRunner().invoke(main, ['apply', '1'], catch_exceptions=False)
    with open('foo.py') as f:
        assert f.read() != file_to_mutate_contents


def test_full_run_no_surviving_mutants(filesystem):
    CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>
""".strip() == result.output.strip()


def test_full_run_no_surviving_mutants_junit(filesystem):
    CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['junitxml'], catch_exceptions=False)
    print(repr(result.output))
    root = ET.fromstring(result.output.strip())
    assert int(root.attrib['tests']) == EXPECTED_MUTANTS
    assert int(root.attrib['failures']) == 0
    assert int(root.attrib['errors']) == 0
    assert int(root.attrib['disabled']) == 0


def test_full_run_one_surviving_mutant(filesystem):
    with open(os.path.join(str(filesystem), "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>


Survived 🙁 (1)

---- foo.py (1) ----

1
""".strip() == result.output.strip()


@pytest.mark.parametrize(
    "expected, source_path, tests_dirs",
    [
        (["foo.py"], "foo.py", []),
        ([os.path.join(".", "foo.py"),
          os.path.join(".", "tests", "test_foo.py")], ".", []),
        ([os.path.join(".", "foo.py")], ".", [os.path.join(".", "tests")])
    ]
)
def test_python_source_files(expected, source_path, tests_dirs, filesystem):
    assert list(python_source_files(source_path, tests_dirs)) == expected


def test_full_run_one_surviving_mutant_junit(filesystem):
    with open(os.path.join(str(filesystem), "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['junitxml'], catch_exceptions=False)
    print(repr(result.output))
    root = ET.fromstring(result.output.strip())
    assert int(root.attrib['tests']) == EXPECTED_MUTANTS
    assert int(root.attrib['failures']) == 1
    assert int(root.attrib['errors']) == 0
    assert int(root.attrib['disabled']) == 0


def test_popen_streaming_output_timeout():
    start = time.time()
    with pytest.raises(CompatTimeoutError):
        popen_streaming_output('python -c "import time; time.sleep(4)"', lambda line: line, timeout=0.1)

    assert time.time() - start < 3


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


@pytest.mark.usefixtures('filesystem')
def test_read_coverage_data():
    assert read_coverage_data(False) is None
    assert isinstance(read_coverage_data(True), CoverageData)
