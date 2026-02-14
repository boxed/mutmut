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
        report = json.loads(completed_process.stdout)
    except json.JSONDecodeError as e:
        raise Exception(f'type check command did not return JSON. Got: {completed_process.stdout} (stderr: {completed_process.stderr})')

    if 'pyrefly' in type_check_command:
        errors = parse_pyrefly_report(report)
    else:
        errors = parse_pyright_report(report)

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