import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import cast


@dataclass
class TypeCheckingError:
    file_path: Path
    line_number: int
    """line number (first line is 1)"""
    error_description: str


def type_checker_environment(type_check_command: list[str], workers: int) -> dict[str, str] | None:
    """Return an environment with MYPY_NUM_WORKERS set, or None if the user already set a worker count."""
    if workers <= 1 or "mypy" not in type_check_command or "MYPY_NUM_WORKERS" in os.environ:
        return None
    if any(arg == "-n" or arg.startswith(("--num-workers", "-n=")) for arg in type_check_command):
        return None
    return {**os.environ, "MYPY_NUM_WORKERS": str(workers)}


def run_type_checker(type_check_command: list[str], workers: int = 1) -> list[TypeCheckingError]:
    errors = []

    completed_process = subprocess.run(
        type_check_command,
        capture_output=True,
        encoding="utf-8",
        env=type_checker_environment(type_check_command, workers),
    )

    try:
        if "mypy" in type_check_command:
            report = [json.loads(line) for line in completed_process.stdout.splitlines()]
        else:
            report = json.loads(completed_process.stdout)
    except json.JSONDecodeError:
        raise Exception(
            f"type check command did not return JSON. Got: {completed_process.stdout} (stderr: {completed_process.stderr})"
        )

    if "pyrefly" in type_check_command:
        errors = parse_pyrefly_report(cast(dict[str, Any], report))
    elif "mypy" in type_check_command:
        errors = parse_mypy_report(report)
    elif "ty" in type_check_command:
        errors = parse_ty_report(report)
    else:
        errors = parse_pyright_report(cast(dict[str, Any], report))

    return errors


def parse_pyright_report(result: dict[str, Any]) -> list[TypeCheckingError]:
    if "generalDiagnostics" not in result:
        raise Exception(f'Invalid pyright report. Could not find key "generalDiagnostics". Found: {set(result.keys())}')

    errors = []
    for diagnostic in result["generalDiagnostics"]:
        errors.append(
            TypeCheckingError(
                file_path=Path(diagnostic["file"]),
                line_number=diagnostic["range"]["start"]["line"] + 1,
                error_description=diagnostic["message"],
            )
        )

    return errors


def parse_pyrefly_report(result: dict[str, Any]) -> list[TypeCheckingError]:
    if "errors" not in result:
        raise Exception(f'Invalid pyrefly report. Could not find key "errors". Found: {set(result.keys())}')

    errors = []

    for error in result["errors"]:
        errors.append(
            TypeCheckingError(
                file_path=Path(error["path"]).absolute(),
                line_number=error["line"],
                error_description=error["concise_description"],
            )
        )

    return errors


def parse_mypy_report(result: list[dict[str, Any]]) -> list[TypeCheckingError]:
    errors = []

    for diagnostic in result:
        if diagnostic["severity"] != "error":
            continue
        errors.append(
            TypeCheckingError(
                file_path=Path(diagnostic["file"]).absolute(),
                line_number=diagnostic["line"],
                error_description=diagnostic["message"],
            )
        )

    return errors


def parse_ty_report(result: list[dict[str, Any]]) -> list[TypeCheckingError]:
    errors = []

    for diagnostic in result:
        # assuming the gitlab code quality report format, these severities seem okay
        # https://docs.gitlab.com/ci/testing/code_quality/#code-quality-report-format
        if diagnostic["severity"] not in ("major", "critical", "blocker"):
            continue
        errors.append(
            TypeCheckingError(
                file_path=Path(diagnostic["location"]["path"]).absolute(),
                line_number=diagnostic["location"]["positions"]["begin"]["line"],
                error_description=diagnostic["description"],
            )
        )

    return errors
