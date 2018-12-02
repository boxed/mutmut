# coding=utf-8
import os
import shutil
import sys
from datetime import datetime

import pytest

from mutmut.__main__ import main, python_source_files, popen_streaming_output
from click.testing import CliRunner

pytestmark = [pytest.mark.skipif(sys.version_info < (3, 0), reason="Don't check Python 3 syntax in Python 2")]

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
def filesystem():
    shutil.rmtree('test_fs', ignore_errors=True)
    os.mkdir('test_fs')
    with open('test_fs/foo.py', 'w') as f:
        f.write(file_to_mutate_contents)

    os.mkdir('test_fs/tests')
    with open('test_fs/tests/test_foo.py', 'w') as f:
        f.write(test_file_contents)

    os.chdir('test_fs')
    yield
    os.chdir('..')
    shutil.rmtree('test_fs')

    # This is a hack to get pony to forget about the old db file
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


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


@pytest.mark.usefixtures('filesystem')
def test_python_source_files():
    assert list(python_source_files('foo.py', [])) == ['foo.py']
    assert list(python_source_files('.', [])) == ['./foo.py', './tests/test_foo.py']
    assert list(python_source_files('.', ['./tests'])) == ['./foo.py']


@pytest.mark.skipif(in_travis, reason='This test does not work on TravisCI')
def test_timeout():
    start = datetime.now()

    with pytest.raises(TimeoutError):
        popen_streaming_output('python -c "import time; time.sleep(4)"', lambda line: line, timeout=0.1)

    assert (datetime.now() - start).total_seconds() < 3
