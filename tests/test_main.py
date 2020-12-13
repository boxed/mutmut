# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from os import (
    mkdir,
)
from os.path import join
from time import time
from unittest.mock import (
    call,
    MagicMock,
)

import pytest
from click.testing import CliRunner

from mutmut import (
    compute_exit_code,
    popen_streaming_output,
    Progress,
    python_source_files,
    read_coverage_data,
)
from mutmut.__main__ import climain

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

EXPECTED_MUTANTS = 14

PYTHON = '"{}"'.format(sys.executable)

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
def filesystem(tmpdir):
    create_filesystem(tmpdir, file_to_mutate_contents, test_file_contents)

    yield tmpdir

    # This is a hack to get pony to forget about the old db file
    # otherwise Pony thinks we've already created the tables
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


@pytest.fixture
def single_mutant_filesystem(tmpdir):
    create_filesystem(tmpdir, "def foo():\n    return 1\n", "from foo import *\ndef test_foo():\n    assert foo() == 1")

    yield tmpdir

    # This is a hack to get pony to forget about the old db file
    # otherwise Pony thinks we've already created the tables
    import mutmut.cache
    mutmut.cache.db.provider = None
    mutmut.cache.db.schema = None


def create_filesystem(tmpdir, file_to_mutate_contents, test_file_contents):
    test_dir = str(tmpdir)
    os.chdir(test_dir)

    # hammett is almost 5x faster than pytest. Let's use that instead.
    with open(join(test_dir, 'setup.cfg'), 'w') as f:
        f.write("""
[mutmut]
runner=python -m hammett -x
""")

    with open(join(test_dir, "foo.py"), 'w') as f:
        f.write(file_to_mutate_contents)

    os.mkdir(join(test_dir, "tests"))

    with open(join(test_dir, "tests", "test_foo.py"), 'w') as f:
        f.write(test_file_contents)


def test_compute_return_code():
    # mock of Config for ease of testing
    class MockProgress(Progress):
        def __init__(self, killed_mutants, surviving_mutants,
                     surviving_mutants_timeout, suspicious_mutants):
            super(MockProgress, self).__init__(total=0, output_legend={})
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
    assert read_coverage_data() == {}


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
    tmpdir = str(tmpdir)
    # arrange
    paths_to_exclude = ['entities*']

    project_dir = join(tmpdir, 'project')
    service_dir = join(project_dir, 'services')
    entities_dir = join(project_dir, 'entities')
    mkdir(project_dir)
    mkdir(service_dir)
    mkdir(entities_dir)

    with open(join(service_dir, 'entities.py'), 'w'):
        pass

    with open(join(service_dir, 'main.py'), 'w'):
        pass

    with open(join(service_dir, 'utils.py'), 'w'):
        pass

    with open(join(entities_dir, 'user.py'), 'w'):
        pass

    # act, assert
    assert set(python_source_files(project_dir, [], paths_to_exclude)) == {
        os.path.join(project_dir, 'services', 'main.py'),
        os.path.join(project_dir, 'services', 'utils.py'),
    }


def test_popen_streaming_output_timeout():
    start = time()
    with pytest.raises(TimeoutError):
        popen_streaming_output(
            PYTHON + ' -c "import time; time.sleep(4)"',
            lambda line: line, timeout=0.1,
        )

    assert (time() - start) < 3


def test_popen_streaming_output_stream():
    mock = MagicMock()
    popen_streaming_output(
        PYTHON + ' -c "print(\'first\'); print(\'second\')"',
        callback=mock
    )
    if os.name == 'nt':
        mock.assert_has_calls([call('first\r\n'), call('second\r\n')])
    else:
        mock.assert_has_calls([call('first\n'), call('second\n')])

    mock = MagicMock()
    popen_streaming_output(
        PYTHON + ' -c "import time; print(\'first\'); print(\'second\'); print(\'third\')"',
        callback=mock
    )
    if os.name == 'nt':
        mock.assert_has_calls([call('first\r\n'), call('second\r\n'), call('third\r\n')])
    else:
        mock.assert_has_calls([call('first\n'), call('second\n'), call('third\n')])

    mock = MagicMock()
    popen_streaming_output(
        PYTHON + ' -c "exit(0);"',
        callback=mock)
    mock.assert_not_called()


def test_simple_apply(filesystem):
    result = CliRunner().invoke(climain, ['run', '-s', '--paths-to-mutate=foo.py', "--test-time-base=15.0"], catch_exceptions=False)
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


Suspicious 🤔 ({EXPECTED_MUTANTS})

---- foo.py ({EXPECTED_MUTANTS}) ----

1-{EXPECTED_MUTANTS}
""".format(EXPECTED_MUTANTS=EXPECTED_MUTANTS).strip()


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


def test_use_coverage(filesystem):
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
    subprocess.run([sys.executable, "-m", "pytest", "--cov=.", "foo.py"])
    assert os.path.isfile('.coverage')

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0", "--use-coverage"], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert '13/13  🎉 13  ⏰ 0  🤔 0  🙁 0' in repr(result.output)

    # remove existent path to check if an exception is thrown
    os.unlink(os.path.join(str(filesystem), 'foo.py'))
    with pytest.raises(ValueError,
                       match=r'^Filepaths in .coverage not recognized, try recreating the .coverage file manually.$'):
        CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0", "--use-coverage"],
                           catch_exceptions=False)


def test_use_patch_file(filesystem):
    patch_contents = """diff --git a/foo.py b/foo.py
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
\\ No newline at end of file
"""
    with open('patch', 'w') as f:
        f.write(patch_contents)

    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--test-time-base=15.0", "--use-patch-file=patch"], catch_exceptions=False)
    print(repr(result.output))
    assert result.exit_code == 0
    assert '2/2  🎉 2  ⏰ 0  🤔 0  🙁 0' in repr(result.output)


def test_pre_and_post_mutation_hook(single_mutant_filesystem, tmpdir):
    test_dir = str(tmpdir)
    os.chdir(test_dir)
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


def test_simple_output(filesystem):
    result = CliRunner().invoke(climain, ['run', '--paths-to-mutate=foo.py', "--simple-output"], catch_exceptions=False)
    print(repr(result.output))
    assert '14/14  KILLED 14  TIMEOUT 0  SUSPICIOUS 0  SURVIVED 0  SKIPPED 0' in repr(result.output)
