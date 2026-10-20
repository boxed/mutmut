import json
from pathlib import Path
from xml.etree import ElementTree

import pytest
from click.testing import CliRunner

from mutmut.__main__ import cli


def write_project(tmp_path: Path, exit_code_by_key: dict[str, int]) -> None:
    (tmp_path / "mutants").mkdir()
    (tmp_path / "foo.py").write_text("def foo():\n    return 1\n")
    (tmp_path / "pyproject.toml").write_text('[tool.mutmut]\nsource_paths = ["foo.py"]\n')
    (tmp_path / "mutants" / "foo.py").write_text(
        "def x_foo__mutmut_orig():\n"
        "    return 1\n" + "".join(f"\ndef x_foo__mutmut_{i}():\n    return {i}\n" for i in range(1, 7))
    )
    (tmp_path / "mutants" / "foo.py.meta").write_text(
        json.dumps(
            {
                "exit_code_by_key": exit_code_by_key,
                "hash_by_function_name": {},
                "type_check_error_by_key": {},
                "durations_by_key": {},
                "estimated_durations_by_key": {},
            }
        )
    )


def test_junitxml_reports_mutant_statuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_project(
        tmp_path,
        {
            "foo.x_foo__mutmut_1": 1,
            "foo.x_foo__mutmut_2": 0,
            "foo.x_foo__mutmut_3": 36,
            "foo.x_foo__mutmut_4": 35,
            "foo.x_foo__mutmut_5": 33,
            "foo.x_foo__mutmut_6": 34,
        },
    )

    result = CliRunner().invoke(
        cli,
        [
            "junitxml",
            "--suspicious-policy=failure",
            "--untested-policy=skipped",
        ],
    )

    assert result.exit_code == 0
    root = ElementTree.fromstring(result.output)
    assert root.attrib["tests"] == "6"
    assert root.attrib["failures"] == "2"
    assert root.attrib["errors"] == "1"
    testsuite = root.find("testsuite")
    assert testsuite is not None
    assert testsuite.attrib["skipped"] == "2"


def test_junitxml_ignores_suspicious_and_untested_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_project(
        tmp_path,
        {
            "foo.x_foo__mutmut_1": 35,
            "foo.x_foo__mutmut_2": 33,
        },
    )

    result = CliRunner().invoke(cli, ["junitxml"])

    assert result.exit_code == 0
    root = ElementTree.fromstring(result.output)
    assert root.attrib["tests"] == "2"
    assert root.attrib["failures"] == "0"
    assert root.attrib["errors"] == "0"
    assert root.attrib["disabled"] == "0"
