# coding=utf-8
import os
import shutil

import pytest

from mutmut import mutate, Context
from mutmut.__main__ import main, mutation_id_separator, python_source_files
from click.testing import CliRunner

file_to_mutate_lines = [
    "a = b + c",
    "d = dict(e=f)",
]
file_to_mutate_contents = '\n'.join(file_to_mutate_lines) + '\n'

test_file_lines = [
    "def test_foo():",
    "   assert True",
]
test_file_contents = '\n'.join(test_file_lines) + '\n'


@pytest.fixture
def test_fs():
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


@pytest.mark.usefixtures('test_fs')
def test_simple_apply():
    CliRunner().invoke(main, ['foo.py', '--apply', '--mutation', mutation_id_separator.join([file_to_mutate_lines[0], '0'])])
    with open('foo.py') as f:
        assert f.read() == mutate(Context(source=file_to_mutate_contents, mutate_id=(file_to_mutate_lines[0], 0)))[0]


@pytest.mark.usefixtures('test_fs')
def test_full_run():
    result = CliRunner().invoke(main, ['foo.py'], catch_exceptions=False)
    print(repr(result.output))
    assert result.output == u'Running tests without mutations... Done\n--- starting mutation ---\n\r0 out of 4  (foo.py)\r1 out of 4  (foo.py a = b + c⤑0)\r2 out of 4  (foo.py a = b + c⤑1)\r3 out of 4  (foo.py d = dict(e=f)⤑0)\r4 out of 4  (foo.py d = dict(e=f)⤑1)'


@pytest.mark.usefixtures('test_fs')
def test_python_source_files():
    assert list(python_source_files('foo.py', [])) == ['foo.py']
    assert list(python_source_files('.', [])) == ['./foo.py', './tests/test_foo.py']
    assert list(python_source_files('.', ['./tests'])) == ['./foo.py']
