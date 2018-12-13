#!/usr/bin/python
# -*- coding: utf-8 -*-

"""pytests for :mod:`mutmut.__main__`"""

import os
import sys

import pytest
from click.testing import CliRunner

from mutmut.__main__ import main
from mutmut.file_collection import python_source_files

pytestmark = [pytest.mark.skipif(sys.version_info < (3, 0), reason="Don't check Python 3 syntax in Python 2")]


file_to_mutate_lines = [
    "def foo(a, b):",
    "    return a < b",
    "e = 1",
    "f = 3",
    "d = dict(e=f)",

]

if sys.version_info >= (3, 6):   # pragma: no cover (python 2 specific)
    file_to_mutate_lines.append("g: int = 2")
else:
    file_to_mutate_lines.append("g = 2")


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

    test_foo = tmpdir.mkdir(os.path.join("test_fs", "tests")).join(
        "test_foo.py")
    test_foo.write(test_file_contents)

    os.chdir(str(tmpdir.join('test_fs')))
    yield
    os.chdir('..')
    # This is a hack to get pony to forget about the old db file
    import mutmut.cache
    mutmut.cache.DB.provider = None
    mutmut.cache.DB.schema = None


@pytest.mark.usefixtures('filesystem')
def test_simple_apply():
    result = CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    CliRunner().invoke(main, ['apply', '1'], catch_exceptions=False)
    with open('foo.py') as f:
        assert f.read() != file_to_mutate_contents


@pytest.mark.usefixtures('filesystem')
def test_full_run_no_surviving_mutants():
    CliRunner().invoke(main, ['run', '--paths-to-mutate=foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>
""".strip() == result.output.strip()


@pytest.mark.usefixtures('filesystem')
def test_full_run_one_surviving_mutant():
    with open('tests/test_foo.py', 'w') as f:
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
@pytest.mark.usefixtures('filesystem')
def test_python_source_files(expected, source_path, tests_dirs):
    assert expected == list(python_source_files(source_path, tests_dirs))
