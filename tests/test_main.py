# coding=utf-8
import os
import shutil
from datetime import datetime

import pytest

from mutmut import mutate, Context, mutation_id_separator
from mutmut.__main__ import main, python_source_files, popen_streaming_output
from click.testing import CliRunner

file_to_mutate_lines = [
    "def foo(a, b):",
    "   return a < b",
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


@pytest.mark.usefixtures('filesystem')
def test_simple_apply():
    CliRunner().invoke(main, ['foo.py', '--apply', '--mutation', mutation_id_separator.join([file_to_mutate_lines[0], '0'])])
    with open('foo.py') as f:
        assert f.read() == mutate(Context(source=file_to_mutate_contents, mutate_id=(file_to_mutate_lines[0], 0)))[0]


@pytest.mark.usefixtures('filesystem')
def test_full_run_no_surviving_mutants():
    CliRunner().invoke(main, ['foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['foo.py', '--print-results'], catch_exceptions=False)
    print(repr(result.output))
    assert result.output.strip() == u"""
Timed out ⏰

Suspicious 🤔

Survived 🙁
""".strip()


@pytest.mark.usefixtures('filesystem')
def test_full_run_one_surviving_mutant():
    with open('tests/test_foo.py', 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    CliRunner().invoke(main, ['foo.py'], catch_exceptions=False)
    result = CliRunner().invoke(main, ['foo.py', '--print-results'], catch_exceptions=False)
    print(repr(result.output))
    assert result.output.strip() == u"""
Timed out ⏰

Suspicious 🤔

Survived 🙁
mutmut foo.py --apply --mutation "return a < b⤑0"
""".strip()


@pytest.mark.usefixtures('filesystem')
def test_python_source_files():
    assert list(python_source_files('foo.py', [])) == ['foo.py']
    assert list(python_source_files('.', [])) == ['./foo.py', './tests/test_foo.py']
    assert list(python_source_files('.', ['./tests'])) == ['./foo.py']


def test_timeout():
    start = datetime.now()

    with pytest.raises(TimeoutError):
        popen_streaming_output('python -c "import time; time.sleep(4)"', lambda line: line, timeout=0.1)

    assert (datetime.now() - start).total_seconds() < 3
