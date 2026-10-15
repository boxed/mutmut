import json
import subprocess
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from mutmut.mutation.file_mutation import filter_mutants_with_type_checker
from mutmut.type_checking import TypeCheckingError
from mutmut.type_checking import parse_mypy_report
from mutmut.type_checking import parse_pyrefly_report
from mutmut.type_checking import run_type_checker

MYPY_COMMAND = ["mypy", "src", "--output", "json"]


def _fake_completed_process(monkeypatch, stdout: str, returncode: int = 0, stderr: str = "") -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("mutmut.type_checking.subprocess.run", fake_run)


def test_run_type_checker_mypy_without_errors(monkeypatch):
    # mypy prints a lone newline (and exits with 0) when it found no type errors at all
    _fake_completed_process(monkeypatch, stdout="\n", returncode=0)

    assert run_type_checker(MYPY_COMMAND) == []


def test_run_type_checker_mypy_with_errors(monkeypatch):
    error = {
        "file": "src/mod.py",
        "line": 2,
        "column": 11,
        "message": 'Incompatible return value type (got "int", expected "str")',
        "hint": None,
        "code": "return-value",
        "severity": "error",
    }
    # mypy prints one JSON object per line and exits with 1 when it found type errors
    _fake_completed_process(monkeypatch, stdout=f"{json.dumps(error)}\n{json.dumps(error)}\n", returncode=1)

    errors = run_type_checker(MYPY_COMMAND)

    assert [(e.file_path.name, e.line_number) for e in errors] == [("mod.py", 2), ("mod.py", 2)]


def test_run_type_checker_mypy_still_raises_on_non_json_output(monkeypatch):
    # a fatal mypy failure (exit code 2) must stay loud and not be mistaken for "no errors"
    _fake_completed_process(
        monkeypatch,
        stdout="Found 1 error in 1 file (errors prevented further checking)\n",
        returncode=2,
        stderr="mypy: error: Cannot read file 'src': No such file or directory",
    )

    with pytest.raises(Exception, match="type check command did not return JSON"):
        run_type_checker(MYPY_COMMAND)


def test_mypy_parsing():
    mypy_output = [
        {
            "file": "src/type_checking/__init__.py",
            "line": 40,
            "column": 20,
            "message": 'Incompatible types in assignment (expression has type "None", variable has type "str")',
            "hint": None,
            "code": "assignment",
            "severity": "error",
        },
        {
            "file": "src/type_checking/__init__.py",
            "line": 73,
            "column": 11,
            "message": 'Unsupported left operand type for - ("str")',
            "hint": None,
            "code": "operator",
            "severity": "error",
        },
        {
            "file": "src/type_checking/__init__.py",
            "line": 114,
            "column": 4,
            "message": "By default the bodies of untyped functions are not checked, consider using --check-untyped-defs",
            "hint": None,
            "code": "annotation-unchecked",
            "severity": "note",
        },
    ]

    result = parse_mypy_report(mypy_output)
    _make_pahts_relative(result)

    assert result == snapshot(
        [
            TypeCheckingError(
                file_path=Path("src/type_checking/__init__.py"),
                line_number=40,
                error_description='Incompatible types in assignment (expression has type "None", variable has type "str")',
            ),
            TypeCheckingError(
                file_path=Path("src/type_checking/__init__.py"),
                line_number=73,
                error_description='Unsupported left operand type for - ("str")',
            ),
        ]
    )


def test_pyrefly_parsing():
    pyrefly_output = {
        "errors": [
            {
                "line": 40,
                "column": 21,
                "stop_line": 40,
                "stop_column": 25,
                "path": "src/type_checking/__init__.py",
                "code": -2,
                "name": "bad-assignment",
                "description": "`None` is not assignable to `str`",
                "concise_description": "`None` is not assignable to `str`",
                "severity": "error",
            },
            {
                "line": 73,
                "column": 12,
                "stop_line": 73,
                "stop_column": 25,
                "path": "src/type_checking/__init__.py",
                "code": -2,
                "name": "unsupported-operation",
                "description": "`-` is not supported between `str` and `Literal['2']`\n  Cannot find `__sub__` or `__rsub__`",
                "concise_description": "`-` is not supported between `str` and `Literal['2']`",
                "severity": "error",
            },
        ]
    }

    result = parse_pyrefly_report(pyrefly_output)
    _make_pahts_relative(result)

    assert result == snapshot(
        [
            TypeCheckingError(
                file_path=Path("src/type_checking/__init__.py"),
                line_number=40,
                error_description="`None` is not assignable to `str`",
            ),
            TypeCheckingError(
                file_path=Path("src/type_checking/__init__.py"),
                line_number=73,
                error_description="`-` is not supported between `str` and `Literal['2']`",
            ),
        ]
    )


def test_filter_mutants_ignores_type_errors_in_files_without_mutants(tmp_path, monkeypatch):
    project = tmp_path
    copied_file = project / "mutants" / "src" / "consumer.py"
    copied_file.parent.mkdir(parents=True)
    copied_file.write_text("def use_kwargs(kwargs):\n    return kwargs\n")
    error = TypeCheckingError(
        file_path=copied_file,
        line_number=2,
        error_description="Unpacked keyword argument object is not assignable",
    )

    monkeypatch.chdir(project)
    monkeypatch.setattr("mutmut.mutation.file_mutation.run_type_checker", lambda command: [error])

    assert filter_mutants_with_type_checker() == {}


def test_filter_mutants_still_raises_for_unowned_errors_in_mutated_files(tmp_path, monkeypatch):
    project = tmp_path
    mutated_file = project / "mutants" / "src" / "module.py"
    mutated_file.parent.mkdir(parents=True)
    mutated_file.write_text(
        "from mutmut.mutation import _mutmut_mutated\n"
        "\n"
        "def helper(value):\n"
        "    return value\n"
        "\n"
        "def x_mutate_me__mutmut_1():\n"
        "    return 2\n"
    )
    error = TypeCheckingError(
        file_path=mutated_file,
        line_number=3,
        error_description="helper type changed unexpectedly",
    )

    monkeypatch.chdir(project)
    monkeypatch.setattr("mutmut.mutation.file_mutation.run_type_checker", lambda command: [error])

    with pytest.raises(Exception, match="Could not find mutant for type error"):
        filter_mutants_with_type_checker()


def _make_pahts_relative(errors: list[TypeCheckingError]):
    cwd = Path(".").resolve()
    for error in errors:
        # make sure that we mapped the relative paths to absolute paths
        assert cwd in error.file_path.parents
        # then convert it to relative path, so it's easy to use snapshot(...)
        error.file_path = error.file_path.relative_to(cwd)
