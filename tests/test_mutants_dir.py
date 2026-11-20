"""End-to-end tests for configuring a custom ``mutants_dir``."""

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from click.testing import CliRunner

import mutmut
from mutmut.__main__ import _changed_dependency_files
from mutmut.__main__ import _run
from mutmut.__main__ import cli
from mutmut.stats import load_stats


@contextmanager
def _sample_project(
    monkeypatch: pytest.MonkeyPatch,
    project_dir: Path,
    *,
    pkg_name: str,
    mutants_dir: str,
    extra_config: str = "",
):
    (project_dir / "src" / pkg_name).mkdir(parents=True)
    (project_dir / "tests").mkdir(parents=True)
    (project_dir / "src" / pkg_name / "__init__.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\ndef unused() -> int:\n    return 42\n"
    )
    (project_dir / "tests" / f"test_{pkg_name}.py").write_text(
        f"from {pkg_name} import add\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n"
    )
    (project_dir / "pyproject.toml").write_text(
        f'[tool.mutmut]\nsource_paths = ["src"]\nmutants_dir = "{mutants_dir}"\n{extra_config}'
    )

    saved_sys_path = list(sys.path)
    monkeypatch.chdir(project_dir)
    mutmut._reset_globals()
    try:
        yield
    finally:
        sys.path[:] = saved_sys_path
        sys.modules.pop(pkg_name, None)
        sys.modules.pop(f"test_{pkg_name}", None)
        mutmut._reset_globals()


@pytest.mark.skipif(os.name == "nt", reason="Forking not supported on Windows")
class TestCustomMutantsDir:
    def test_out_of_tree_mutants_dir_end_to_end(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        pkg_name = "mutants_dir_ext_pkg"
        project_dir = tmp_path / "project"
        external_dir = tmp_path / "external_mutants"

        with _sample_project(monkeypatch, project_dir, pkg_name=pkg_name, mutants_dir=str(external_dir)):
            _run([], max_children=2)

            assert not (project_dir / "mutants").exists()
            assert (external_dir / "mutmut-stats.json").is_file()
            assert (external_dir / "src" / pkg_name / "__init__.py.meta").is_file()
            assert (external_dir / "src" / pkg_name / "__init__.py.spans").is_file()

            runner = CliRunner()

            results_res = runner.invoke(cli, ["results"])
            assert results_res.exit_code == 0
            assert f"{pkg_name}.x_unused__mutmut_1: no tests" in results_res.output

            show_res = runner.invoke(cli, ["show", f"{pkg_name}.x_unused__mutmut_1"])
            assert show_res.exit_code == 0
            assert "-    return 42" in show_res.output
            assert "+    return 43" in show_res.output

            tests_res = runner.invoke(cli, ["tests-for-mutant", f"{pkg_name}.x_add__mutmut_1"])
            assert tests_res.exit_code == 0
            assert f"tests/test_{pkg_name}.py::test_add" in tests_res.output

            badge_path = tmp_path / "badge.json"
            missing_badge_res = runner.invoke(cli, ["badge", "--output", str(badge_path)])
            assert missing_badge_res.exit_code != 0
            assert str(external_dir / "mutmut-cicd-stats.json") in missing_badge_res.output

            export_res = runner.invoke(cli, ["export-cicd-stats"])
            assert export_res.exit_code == 0
            cicd_stats = external_dir / "mutmut-cicd-stats.json"
            assert cicd_stats.is_file()
            assert str(cicd_stats) in export_res.output

            badge_res = runner.invoke(cli, ["badge", "--output", str(badge_path)])
            assert badge_res.exit_code == 0
            badge_data = json.loads(badge_path.read_text())
            assert badge_data["schemaVersion"] == 1
            assert badge_data["label"] == "mutation"

            apply_res = runner.invoke(cli, ["apply", f"{pkg_name}.x_unused__mutmut_1"])
            assert apply_res.exit_code == 0
            assert "return 43" in (project_dir / "src" / pkg_name / "__init__.py").read_text()

    def test_relative_nested_mutants_dir_with_forkserver(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        pkg_name = "mutants_dir_fs_pkg"
        project_dir = tmp_path / "project_fs"

        with _sample_project(
            monkeypatch,
            project_dir,
            pkg_name=pkg_name,
            mutants_dir=".cache/mutants",
            extra_config='process_isolation = "forkserver"\n',
        ):
            _run([], max_children=2)

            assert not (project_dir / "mutants").exists()
            cache_dir = project_dir / ".cache" / "mutants"
            assert (cache_dir / "mutmut-stats.json").is_file()
            meta = json.loads((cache_dir / "src" / pkg_name / "__init__.py.meta").read_text())
            assert meta["exit_code_by_key"][f"{pkg_name}.x_add__mutmut_1"] == 1
            assert meta["exit_code_by_key"][f"{pkg_name}.x_unused__mutmut_1"] == 33

    @pytest.mark.parametrize("mode", ["absolute", "relative_parent", "symlink"])
    def test_custom_mutants_dir_with_mutate_only_covered_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
    ):
        pkg_name = f"mutants_dir_cov_{mode}_pkg"
        project_dir = tmp_path / f"project_{mode}"
        target_dir = tmp_path / f"cov_mutants_{mode}"

        if mode == "absolute":
            mutants_dir = str(target_dir)
        elif mode == "relative_parent":
            mutants_dir = f"../{target_dir.name}"
        else:
            target_dir.mkdir()
            link_dir = tmp_path / f"link_{mode}"
            link_dir.symlink_to(target_dir)
            mutants_dir = str(link_dir)

        with _sample_project(
            monkeypatch,
            project_dir,
            pkg_name=pkg_name,
            mutants_dir=mutants_dir,
            extra_config="mutate_only_covered_lines = true\n",
        ):
            _run([], max_children=2)

            assert not (project_dir / "mutants").exists()
            meta = json.loads((target_dir / "src" / pkg_name / "__init__.py.meta").read_text())
            assert f"{pkg_name}.x_add__mutmut_1" in meta["exit_code_by_key"]
            assert f"{pkg_name}.x_unused__mutmut_1" not in meta["exit_code_by_key"]

    @pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
    def test_git_change_detection_ignores_custom_mutants_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        pkg_name = "mutants_dir_git_pkg"
        project_dir = tmp_path / "project_git"

        with _sample_project(monkeypatch, project_dir, pkg_name=pkg_name, mutants_dir=".mutmut-cache"):
            for cmd in [
                ["init", "-q"],
                ["config", "user.email", "test@example.com"],
                ["config", "user.name", "Test"],
                ["config", "commit.gpgsign", "false"],
                ["add", "."],
                ["commit", "-q", "-m", "init"],
            ]:
                subprocess.run(["git", *cmd], cwd=project_dir, check=True)

            _run([], max_children=2)

            mutmut._reset_globals()
            assert load_stats()
            assert _changed_dependency_files() == set()

            sibling_file = project_dir / ".mutmut-cache-extra" / "data.json"
            sibling_file.parent.mkdir()
            sibling_file.write_text("{}")
            assert _changed_dependency_files() == {".mutmut-cache-extra/data.json"}
