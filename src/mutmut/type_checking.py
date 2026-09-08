import json
import subprocess
import tempfile
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


class TypeCheckerProcess:
    """A type checker running in the background.

    Its output goes to temporary files rather than pipes, so it never blocks on a full pipe
    while nobody is reading. ``result()`` waits for it and parses the report."""

    def __init__(self, type_check_command: list[str], cwd: Path | str | None = None) -> None:
        self.command = type_check_command
        self._stdout = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        self._stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        self.process = subprocess.Popen(type_check_command, cwd=cwd, stdout=self._stdout, stderr=self._stderr)

    def result(self) -> list[TypeCheckingError]:
        self.process.wait()
        self._stdout.seek(0)
        self._stderr.seek(0)
        try:
            return parse_type_checker_output(self.command, self._stdout.read(), self._stderr.read())
        finally:
            self._stdout.close()
            self._stderr.close()

    def terminate(self) -> None:
        """Stop the checker if it is still running (its result is not needed)."""
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
        self._stdout.close()
        self._stderr.close()


def start_type_checker(type_check_command: list[str], cwd: Path | str | None = None) -> TypeCheckerProcess:
    return TypeCheckerProcess(type_check_command, cwd=cwd)


def run_type_checker(type_check_command: list[str]) -> list[TypeCheckingError]:
    return start_type_checker(type_check_command).result()


def parse_type_checker_output(type_check_command: list[str], stdout: str, stderr: str) -> list[TypeCheckingError]:
    try:
        if "mypy" in type_check_command:
            report = [json.loads(line) for line in stdout.splitlines()]
        else:
            report = json.loads(stdout)
    except json.JSONDecodeError:
        raise Exception(f"type check command did not return JSON. Got: {stdout} (stderr: {stderr})")

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
