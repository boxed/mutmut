"""End-to-end smoke test for the hot-fork process-isolation runner.

The hot-fork orchestrator forks itself and installs signal handlers, so it is
exercised in a subprocess (with a hard timeout) rather than in-process, keeping
any hang or signal interaction out of the pytest session running this test.
"""

import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
E2E_PROJECTS = REPO_ROOT / "e2e_projects"


def _read_verdicts(project_path: Path) -> dict[str, int]:
    verdicts: dict[str, int] = {}
    for meta in sorted((project_path / "mutants").rglob("*.meta")):
        data = json.loads(meta.read_text())
        verdicts.update(data["exit_code_by_key"])
    return verdicts


def test_hot_fork_runs_end_to_end(tmp_path: Path):
    project = tmp_path / "hot_fork_basic"
    shutil.copytree(E2E_PROJECTS / "hot_fork_basic", project)

    result = subprocess.run(
        [sys.executable, "-m", "mutmut", "run"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=240,
    )

    assert result.returncode == 0, f"mutmut run failed:\n{result.stdout}\n{result.stderr}"

    verdicts = _read_verdicts(project)
    assert verdicts, "no mutant results were written"

    counts = Counter(verdicts.values())
    # 0 = survived, 1 = killed, 33 = no tests. The tested functions (add/sub/mul)
    # must produce some killed mutants, and `untested` must produce no-tests ones.
    assert counts.get(1, 0) > 0, f"expected some killed mutants, got {dict(counts)}"
    assert counts.get(33, 0) > 0, f"expected some no-tests mutants, got {dict(counts)}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
