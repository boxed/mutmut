"""End-to-end test for the `generate` command.

`generate` regenerates mutants and refreshes hashes/stats without running the
mutation-testing loop. It is exercised in a subprocess (with a timeout) so any
signal/fork interaction stays out of the pytest session.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
E2E_PROJECTS = REPO_ROOT / "e2e_projects"


def test_generate_creates_mutant_metadata(tmp_path: Path):
    project = tmp_path / "hot_fork_basic"
    shutil.copytree(E2E_PROJECTS / "hot_fork_basic", project)
    # Use the default fork isolation for this smoke test.
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('process_isolation = "hot-fork"\n', ""))

    result = subprocess.run(
        [sys.executable, "-m", "mutmut", "generate", "--no-invalidate-callers"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, f"mutmut generate failed:\n{result.stdout}\n{result.stderr}"

    metas = list((project / "mutants").rglob("*.meta"))
    assert metas, "generate did not produce any mutant metadata"

    # generate must populate mutant keys and per-function hashes, without running
    # the mutation loop (so verdicts stay uncommitted / None here).
    data = json.loads(metas[0].read_text())
    assert data["exit_code_by_key"], "no mutants were recorded"
    assert data["hash_by_function_name"], "function hashes were not written"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
