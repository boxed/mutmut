#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import time
from subprocess import TimeoutExpired

import pytest

from mutmut.__main__ import main
from mutmut.file_collection import get_python_source_files
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

    os.chdir(str(tmpdir.join('test_fs')))
    yield
    os.chdir('..')
    # This is a hack to get pony to forget about the old db file
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


@pytest.mark.usefixtures('filesystem')
def test_full_run_no_surviving_mutants(capsys):
    main(['foo.py'])
    captured = capsys.readouterr()
    assert "ALIVE:1" not in captured.out


@pytest.mark.usefixtures('filesystem')
def test_full_run_one_surviving_mutant(capsys):
    with open('tests/test_foo.py', 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))
    main(['foo.py'])
    captured = capsys.readouterr()
    assert "ALIVE:1" in captured.out


@pytest.mark.parametrize("expected, source_path, tests_dirs",
                         [
                             (["foo.py"], "foo.py", []),
                             ([os.path.join(".", "foo.py"),
                               os.path.join(".", "tests", "test_foo.py")], ".",
                              []),
                             ([os.path.join(".", "foo.py")], ".",
                              [os.path.join(".", "tests")])
                         ]
                         )
@pytest.mark.usefixtures('filesystem')
def test_python_source_files(expected, source_path, tests_dirs):
    assert expected == list(get_python_source_files(source_path, tests_dirs))


def mock_callback_func(line):
    """test call back function to be thrown into ``popen_streaming_output``"""
    print(line)


def test_timeout(capsys):
    """ensure that ``popen_streaming_output`` can properly timeout"""
    start = time.time()
    with pytest.raises(TimeoutExpired):
        popen_streaming_output(
            """python -c "import time; time.sleep(4); print('failure')""""",
            mock_callback_func, timeout=0.1
        )
    assert (time.time() - start) < 3
    # ensure we obtained nothing
    captured = capsys.readouterr()
    assert not captured.out


def test_non_timeout(capsys):
    start = time.time()
    popen_streaming_output(
        """python -c "import time; time.sleep(4); print('success')""""",
        mock_callback_func, timeout=10
    )
    assert (time.time() - start) > 4
    # ensure we captured the print of 'success'
    captured = capsys.readouterr()
    assert captured.out == "success\n"
