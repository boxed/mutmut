import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_run_json_output_is_machine_readable():
    project_path = Path("..").parent / "e2e_projects" / "config"
    mutants_path = project_path / "mutants"
    shutil.rmtree(mutants_path, ignore_errors=True)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "nootnoot",
            "run",
            "--format",
            "json",
            "--max-children",
            "1",
        ],
        cwd=project_path,
        check=False,
        text=True,
        capture_output=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)

    assert payload["schema_version"] == 1
    assert "summary" in payload
    assert "mutants" in payload
    assert "events" in payload
    event_names = {event["event"] for event in payload["events"]}
    assert "session_started" in event_names
    assert "session_finished" in event_names
