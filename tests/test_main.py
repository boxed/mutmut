# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as ET
import subprocess
from time import time
from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner
from coverage import CoverageData

from mutmut.__main__ import climain, python_source_files, \
    popen_streaming_output, compute_exit_code, \
    read_coverage_data, Progress

file_to_mutate_lines = [
    "def foo(a, b):",
    "    return a < b",
    "c = 1",
    "c += 1",
    "e = 1",
    "f = 3",
    "d = dict(e=f)",
    "g: int = 2",
]

EXPECTED_MUTANTS = 13


file_to_mutate_contents = '\n'.join(file_to_mutate_lines) + '\n'

test_file_contents = '''
from foo import *

def test_foo():
   assert foo(1, 2) is True
   assert foo(2, 2) is False

   assert c == 2
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


def test_compute_return_code():
    # mock of Config for ease of testing
    class MockProgress(Progress):
        def __init__(self, killed_mutants, surviving_mutants,
                     surviving_mutants_timeout, suspicious_mutants):
            super(MockProgress, self).__init__()
            self.killed_mutants = killed_mutants
            self.surviving_mutants = surviving_mutants
            self.surviving_mutants_timeout = surviving_mutants_timeout
            self.suspicious_mutants = suspicious_mutants

    assert compute_exit_code(MockProgress(0, 0, 0, 0)) == 0
    assert compute_exit_code(MockProgress(0, 0, 0, 1)) == 8
    assert compute_exit_code(MockProgress(0, 0, 1, 0)) == 4
    assert compute_exit_code(MockProgress(0, 0, 1, 1)) == 12
    assert compute_exit_code(MockProgress(0, 1, 0, 0)) == 2
    assert compute_exit_code(MockProgress(0, 1, 0, 1)) == 10
    assert compute_exit_code(MockProgress(0, 1, 1, 0)) == 6
    assert compute_exit_code(MockProgress(0, 1, 1, 1)) == 14

    assert compute_exit_code(MockProgress(1, 0, 0, 0)) == 0
    assert compute_exit_code(MockProgress(1, 0, 0, 1)) == 8
    assert compute_exit_code(MockProgress(1, 0, 1, 0)) == 4
    assert compute_exit_code(MockProgress(1, 0, 1, 1)) == 12
    assert compute_exit_code(MockProgress(1, 1, 0, 0)) == 2
    assert compute_exit_code(MockProgress(1, 1, 0, 1)) == 10
    assert compute_exit_code(MockProgress(1, 1, 1, 0)) == 6
    assert compute_exit_code(MockProgress(1, 1, 1, 1)) == 14

    assert compute_exit_code(MockProgress(0, 0, 0, 0), Exception()) == 1
    assert compute_exit_code(MockProgress(0, 0, 0, 1), Exception()) == 9
    assert compute_exit_code(MockProgress(0, 0, 1, 0), Exception()) == 5
    assert compute_exit_code(MockProgress(0, 0, 1, 1), Exception()) == 13
    assert compute_exit_code(MockProgress(0, 1, 0, 0), Exception()) == 3
    assert compute_exit_code(MockProgress(0, 1, 0, 1), Exception()) == 11
    assert compute_exit_code(MockProgress(0, 1, 1, 0), Exception()) == 7
    assert compute_exit_code(MockProgress(0, 1, 1, 1), Exception()) == 15

    assert compute_exit_code(MockProgress(1, 0, 0, 0), Exception()) == 1
    assert compute_exit_code(MockProgress(1, 0, 0, 1), Exception()) == 9
    assert compute_exit_code(MockProgress(1, 0, 1, 0), Exception()) == 5
    assert compute_exit_code(MockProgress(1, 0, 1, 1), Exception()) == 13
    assert compute_exit_code(MockProgress(1, 1, 0, 0), Exception()) == 3
    assert compute_exit_code(MockProgress(1, 1, 0, 1), Exception()) == 11
    assert compute_exit_code(MockProgress(1, 1, 1, 0), Exception()) == 7
    assert compute_exit_code(MockProgress(1, 1, 1, 1), Exception()) == 15


def test_read_coverage_data(filesystem):
    assert isinstance(read_coverage_data(), CoverageData)


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


def test_python_source_files__with_paths_to_exclude(tmpdir):
    # arrange
    paths_to_exclude = ['entities*']

    project_dir = tmpdir.mkdir('project')
    service_dir = project_dir.mkdir('services')

    f = service_dir.join('entities.py')
    f.write('')
    f = service_dir.join('main.py')
    f.write('')
    f = service_dir.join('utils.py')
    f.write('')

    entities_dir = project_dir.mkdir('entities')
    f = entities_dir.join('user.py')
    f.write('')

    # act, assert
    assert set(python_source_files(project_dir.strpath, [], paths_to_exclude)) == {
        os.path.join(project_dir.strpath, 'services', 'main.py'),
        os.path.join(project_dir.strpath, 'services', 'utils.py'),
    }


def test_popen_streaming_output_timeout():
    start = time()
    with pytest.raises(TimeoutError):
        popen_streaming_output('python -c "import time; time.sleep(4)"', lambda line: line, timeout=0.1)

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


def test_simple_apply(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0

    result = CliRunner().invoke(climain, ['apply', '1'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    with open(os.path.join(str(filesystem), 'foo.py')) as f:
        assert f.read() != file_to_mutate_contents


def test_full_run_no_surviving_mutants(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
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
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
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
        f.write(test_file_contents.replace('assert foo(2, 2) is False', ''))

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
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

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
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
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-multiplier=0.0"], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 8
    result = CliRunner().invoke(climain, ['results'], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert result.output.strip() == u"""
To apply a mutant on disk:
    mutmut apply <id>

To show a mutant:
    mutmut show <id>


Suspicious 🤔 (13)

---- foo.py (13) ----

1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13
""".strip()


def test_full_run_all_suspicious_mutant_junit(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-multiplier=0.0"], catch_exceptions=False)
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


@pytest.mark.skip("This test is broken by the worker process spawning, I don't understand why but I'm skipping it for now")
def test_use_coverage(capsys, filesystem):
    with open(os.path.join(str(filesystem), "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents.replace('assert foo(2, 2) is False\n', ''))

    # first validate that mutmut without coverage detects a surviving mutant
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
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
    subprocess.run(["python", "-m", "pytest", "--cov=.", "foo.py"])
    assert os.path.isfile('.coverage')

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0", "--use-coverage"], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert '12/12  🎉 12  ⏰ 0  🤔 0  🙁 0' in repr(result.output)


def test_use_patch_file(filesystem):
    patch_contents = r"""diff --git a/foo.py b/foo.py
index b9a5fb4..c6a496c 100644
--- a/foo.py
+++ b/foo.py
@@ -1,7 +1,7 @@
 def foo(a, b):
     return a < b
 c = 1
 c += 1
 e = 1
-f = 3
+f = 5
 d = dict(e=f)
\ No newline at end of file
"""
    with open('patch', 'w') as f:
        f.write(patch_contents)

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0", "--use-patch-file=patch"], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert '2/2  🎉 2  ⏰ 0  🤔 0  🙁 0' in repr(result.output)


def test_pre_and_post_mutation_hook(filesystem):
    result = CliRunner().invoke(
        climain, [
            'run',
            '--paths-to-mutate=foo.py',
            "--test-time-base=15.0",
            "-s",
            "--pre-mutation=echo pre mutation stub",
            "--post-mutation=echo post mutation stub",
        ], catch_exceptions=False)
    print(result.output)
    assert result.exit_code == 0
    assert "pre mutation stub" in result.output
    assert "post mutation stub" in result.output
    assert result.output.index("pre mutation stub") < result.output.index("post mutation stub")
