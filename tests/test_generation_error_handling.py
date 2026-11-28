import os
import shutil
import signal
from contextlib import contextmanager
from pathlib import Path

import pytest

import mutmut.__main__
from mutmut.__main__ import InvalidGeneratedSyntaxException
from mutmut.__main__ import MutantGenerationWorkerDiedException
from mutmut.__main__ import create_file_mutants
from mutmut.__main__ import create_mutants
from mutmut.configuration import config

source_dir = Path(__file__).parent / "data" / "test_generation"
source_dir = source_dir.relative_to(Path.cwd())


def test_mutant_generation_raises_exception_on_invalid_syntax(monkeypatch):
    mutmut._reset_globals()

    shutil.rmtree("mutants", ignore_errors=True)

    source_files = [
        source_dir / "valid_syntax_1.py",
        source_dir / "valid_syntax_2.py",
        source_dir / "valid_syntax_3.py",
        source_dir / "valid_syntax_4.py",
        source_dir / "invalid_syntax.py",
    ]
    monkeypatch.setattr(mutmut.__main__, "walk_source_files", lambda: source_files)
    monkeypatch.setattr(config(), "should_mutate", lambda _path: True)

    # should raise an exception, because we copy the invalid_syntax.py file and then verify
    # if it is valid syntax
    with pytest.raises(InvalidGeneratedSyntaxException) as excinfo:
        # should raise a warning, because libcst is not able to parse invalid_syntax.py
        with pytest.warns(SyntaxWarning):
            create_mutants(max_children=2)
    assert "invalid_syntax.py" in str(excinfo.value)


@contextmanager
def fail_after(seconds: int):
    def on_timeout(signum, frame):
        raise TimeoutError(f"still running after {seconds}s")

    previous_handler = signal.signal(signal.SIGALRM, on_timeout)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)


def create_file_mutants_or_get_killed(path: Path):
    # Runs in a worker process. Die the way the kernel kills a process that uses too much memory.
    if path.name == "valid_syntax_3.py":
        os.kill(os.getpid(), signal.SIGKILL)
    return create_file_mutants(path)


def test_mutant_generation_fails_when_a_worker_dies(monkeypatch):
    mutmut._reset_globals()

    shutil.rmtree("mutants", ignore_errors=True)

    source_files = [
        source_dir / "valid_syntax_1.py",
        source_dir / "valid_syntax_2.py",
        source_dir / "valid_syntax_3.py",
        source_dir / "valid_syntax_4.py",
    ]
    monkeypatch.setattr(mutmut.__main__, "walk_source_files", lambda: source_files)
    monkeypatch.setattr(mutmut.__main__, "create_file_mutants", create_file_mutants_or_get_killed)
    monkeypatch.setattr(config(), "should_mutate", lambda _path: True)

    # used to wait forever for the result of the killed worker
    with fail_after(30), pytest.raises(MutantGenerationWorkerDiedException) as excinfo:
        create_mutants(max_children=2)
    assert "valid_syntax_3.py" in str(excinfo.value)
    assert "--max-children" in str(excinfo.value)
