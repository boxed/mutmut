# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import xml.etree.ElementTree as ET

import pytest
from click.testing import CliRunner
from coverage import CoverageData

from mutmut.__main__ import climain, python_source_files, read_coverage_data

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

if sys.version_info >= (3, 6):  # pragma: no cover (python 2 specific)
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
    os.chdir(str(test_fs))
    assert os.getcwd() == str(test_fs)

    # using `with` pattern to satisfy the pypy gods
    with open(str(test_fs.join("foo.py")), 'w') as f:
        f.write(file_to_mutate_contents)
    os.mkdir(str(test_fs.join("tests")))
    with open(str(test_fs.join("tests", "test_foo.py")), 'w') as f:
        f.write(test_file_contents)
    yield test_fs

    # This is a hack to get pony to forget about the old db file
    # otherwise Pony thinks we've already created the tables
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


def test_read_coverage_data(filesystem):
    assert read_coverage_data(False) is None
    assert isinstance(read_coverage_data(True), CoverageData)


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


def test_simple_apply(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0

    result = CliRunner().invoke(climain, ['apply', '1'],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    with open(os.path.join(str(filesystem), 'foo.py')) as f:
        assert f.read() != file_to_mutate_contents


def test_full_run_no_surviving_mutants(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    result = CliRunner().invoke(climain, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert result.output.strip() == u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>
""".strip()


def test_full_run_no_surviving_mutants_junit(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0

    result = CliRunner().invoke(climain, ['junitxml'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    root = ET.fromstring(result.output.strip())
    assert int(root.attrib['tests']) == EXPECTED_MUTANTS
    assert int(root.attrib['failures']) == 0
    assert int(root.attrib['errors']) == 0
    assert int(root.attrib['disabled']) == 0


def test_full_run_one_surviving_mutant(filesystem):
    with open(os.path.join(str(filesystem), "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 2

    result = CliRunner().invoke(climain, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert result.output.strip() == u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>


Survived 🙁 (1)

---- foo.py (1) ----

1
""".strip()


def test_full_run_one_surviving_mutant_junit(filesystem):
    with open(os.path.join(str(filesystem), "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 2

    result = CliRunner().invoke(climain, ['junitxml'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    root = ET.fromstring(result.output.strip())
    assert int(root.attrib['tests']) == EXPECTED_MUTANTS
    assert int(root.attrib['failures']) == 1
    assert int(root.attrib['errors']) == 0
    assert int(root.attrib['disabled']) == 0


def test_full_run_all_suspicious_mutant(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-multiplier=0.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 8
    result = CliRunner().invoke(climain, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    if EXPECTED_MUTANTS == 8:  # python3
        assert result.output.strip() == u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>


Suspicious 🤔 (8)

---- foo.py (8) ----

1, 2, 3, 4, 5, 6, 7, 8
""".strip()
    else:  # python2
        assert result.output.strip() == u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>


Suspicious 🤔 (9)

---- foo.py (9) ----

1, 2, 3, 4, 5, 6, 7, 8, 9
""".strip()


def test_full_run_all_suspicious_mutant_junit(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-multiplier=0.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 8
    result = CliRunner().invoke(climain, ['junitxml'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    root = ET.fromstring(result.output.strip())
    assert int(root.attrib['tests']) == EXPECTED_MUTANTS
    assert int(root.attrib['failures']) == 0
    assert int(root.attrib['errors']) == 0
    assert int(root.attrib['disabled']) == 0


def test_use_coverage(capsys, filesystem):
    with open(os.path.join(str(filesystem), "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    # first validate that mutmut without coverage detects a surviving mutant
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 2

    result = CliRunner().invoke(climain, ['junitxml'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    root = ET.fromstring(result.output.strip())
    assert int(root.attrib['tests']) == EXPECTED_MUTANTS
    assert int(root.attrib['failures']) == 1
    assert int(root.attrib['errors']) == 0
    assert int(root.attrib['disabled']) == 0

    # generate a `.coverage` file by invoking pytest
    pytest.main(["--cov=.", "foo.py"])
    assert os.path.isfile('.coverage')

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py',
                                          "--test-time-base=5.0",
                                          "--use-coverage"],
                                catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    if EXPECTED_MUTANTS == 8:  # python3
        assert '7/7  🎉 7  ⏰ 0  🤔 0  🙁 0' in repr(result.output)
    else:  # python2
        assert '8/8  \\U0001f389 8  \\u23f0 0  \\U0001f914 0  \\U0001f641 0' in repr(
            result.output)
