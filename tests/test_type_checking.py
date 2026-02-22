from inline_snapshot import snapshot
from mutmut.type_checking import parse_mypy_report, parse_pyrefly_report

from pathlib import Path
from mutmut.type_checking import TypeCheckingError


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


def _make_pahts_relative(errors: list[TypeCheckingError]):
    cwd = Path(".").resolve()
    for error in errors:
        # make sure that we mapped the relative paths to absolute paths
        assert cwd in error.file_path.parents
        # then convert it to relative path, so it's easy to use snapshot(...)
        error.file_path = error.file_path.relative_to(cwd)
