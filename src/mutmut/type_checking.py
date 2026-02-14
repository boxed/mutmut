from typing import cast
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass


@dataclass
class TypeCheckingError:
    file_path: Path
    line_number: int
    """line number (first line is 1)"""
    error_description: str


def run_type_checker(type_check_command: list[str]) -> list[TypeCheckingError]:
    errors = []

    completed_process = subprocess.run(type_check_command, capture_output=True, encoding='utf-8')

    try:
        if 'mypy' in type_check_command:
            report = [json.loads(line) for line in completed_process.stdout.splitlines()]
        else:
            report = json.loads(completed_process.stdout)
    except json.JSONDecodeError as e:
        raise Exception(f'type check command did not return JSON. Got: {completed_process.stdout} (stderr: {completed_process.stderr})')

    if 'pyrefly' in type_check_command:
        errors = parse_pyrefly_report(cast(dict, report))
    elif 'mypy' in type_check_command:
        errors = parse_mypy_report(report)
    elif 'ty' in type_check_command:
        errors = parse_ty_report(report)
    else:
        errors = parse_pyright_report(cast(dict, report))

    return errors


def parse_pyright_report(result: dict) -> list[TypeCheckingError]:
    if not 'generalDiagnostics' in result:
        raise Exception(f'Invalid pyright report. Could not find key "generalDiagnostics". Found: {set(result.keys())}')

    errors = []
    for diagnostic in result['generalDiagnostics']:
        errors.append(TypeCheckingError(
            file_path=Path(diagnostic['file']),
            line_number=diagnostic['range']['start']['line'] + 1,
            error_description=diagnostic['message'],
        ))
    
    return errors
        
def parse_pyrefly_report(result: dict) -> list[TypeCheckingError]:
    if not 'errors' in result:
        raise Exception(f'Invalid pyrefly report. Could not find key "errors". Found: {set(result.keys())}')

    errors = []

    for error in result['errors']:
        errors.append(TypeCheckingError(
            file_path=Path(error['path']).absolute(),
            line_number=error['line'],
            error_description=error['concise_description'],
        ))

    return errors

def parse_mypy_report(result: list[dict]) -> list[TypeCheckingError]:
    errors = []

    for diagnostic in result:
        if diagnostic['severity'] != 'error':
            continue
        errors.append(TypeCheckingError(
            file_path=Path(diagnostic['file']).absolute(),
            line_number=diagnostic['line'],
            error_description=diagnostic['message'],
        ))

    return errors

def parse_ty_report(result: list[dict]) -> list[TypeCheckingError]:
    errors = []

    for diagnostic in result:
        # assuming the gitlab code quality report format, these severities seem okay
        # https://docs.gitlab.com/ci/testing/code_quality/#code-quality-report-format
        if diagnostic['severity'] not in ('major', 'critical', 'blocker'):
            continue
        errors.append(TypeCheckingError(
            file_path=Path(diagnostic['location']['path']).absolute(),
            line_number=diagnostic['location']['positions']['begin']['line'],
            error_description=diagnostic['description'],
        ))

    return errors