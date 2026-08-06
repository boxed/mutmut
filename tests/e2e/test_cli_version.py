import json
from pathlib import Path

from click.testing import CliRunner

from mutmut import __version__
from mutmut.__main__ import cli
from mutmut.__main__ import mutation_score_to_hex_color


def test_cli_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_mutation_score_to_hex_color_gradient_endpoints():
    assert mutation_score_to_hex_color(0.0) == "#ff0000"
    assert mutation_score_to_hex_color(100.0) == "#00ff00"


def test_badge_command_writes_shields_json(tmp_path: Path):
    stats_path = tmp_path / "mutants" / "mutmut-cicd-stats.json"
    badge_path = tmp_path / "artifacts" / "mutation-score.json"
    stats_path.parent.mkdir(parents=True)
    stats_path.write_text(json.dumps({"killed": 4, "timeout": 1, "total": 10, "skipped": 2}))

    result = CliRunner().invoke(cli, ["badge", "--input", str(stats_path), "--output", str(badge_path)])

    assert result.exit_code == 0
    assert json.loads(badge_path.read_text()) == {
        "schemaVersion": 1,
        "label": "mutation",
        "message": "62.5%",
        "color": "#bfff00",
    }


def test_badge_command_reports_input_errors(tmp_path: Path):
    malformed_path = tmp_path / "broken.json"
    malformed_path.write_text("{")
    malformed_result = CliRunner().invoke(
        cli,
        ["badge", "--input", str(malformed_path), "--output", str(tmp_path / "badge.json")],
    )
    assert malformed_result.exit_code == 1
    assert "does not contain valid JSON" in malformed_result.output
