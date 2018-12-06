#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import time

import pytest

from mutmut.__main__ import main, python_source_files
from mutmut.runner import popen_streaming_output

in_travis = os.environ['PATH'].startswith('/home/travis/')

file_to_mutate_lines = [
    "def foo(a, b):",
    "    return a < b",
    "e = 1",
    "f = 3",
    "d = dict(e=f)",
    "g: int = 2",
]

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
def filesystem(tmpdir):
    foo = tmpdir.mkdir("test_fs").join("foo.py")
    foo.write(file_to_mutate_contents)

    test_foo = tmpdir.mkdir(os.path.join("test_fs", "tests")).join("test_foo.py")
    test_foo.write(test_file_contents)

    os.chdir(tmpdir.join('test_fs'))
    yield
    os.chdir('..')
    # This is a hack to get pony to forget about the old db file
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


@pytest.mark.usefixtures('filesystem')
def test_full_run_no_surviving_mutants(capsys):
    main(['--paths-to-mutate=foo.py'])
    captured = capsys.readouterr()
    assert "ALIVE:     1" not in captured.out


@pytest.mark.usefixtures('filesystem')
def test_full_run_one_surviving_mutant(capsys):
    with open('tests/test_foo.py', 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))
    main(['--paths-to-mutate=foo.py'])
    captured = capsys.readouterr()
    assert "ALIVE:     1" in captured.out


@pytest.mark.usefixtures('filesystem')
def test_python_source_files():
    assert list(python_source_files('foo.py', [])) == ['foo.py']
    assert list(python_source_files('.', [])) == ['./foo.py', './tests/test_foo.py']
    assert list(python_source_files('.', ['./tests'])) == ['./foo.py']


@pytest.mark.skipif(in_travis, reason='This test does not work on TravisCI')
def test_timeout():
    start = time.time()
    with pytest.raises(TimeoutError):
        popen_streaming_output(
            'python -c "import time; time.sleep(4)"',
            lambda line: line, timeout=0.1
        )
    assert (time.time() - start) < 3
