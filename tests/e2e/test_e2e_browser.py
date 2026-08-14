"""End-to-end test for the result browser's dependency/cache UI.

Builds mutants for a tiny project in-process, then drives the Textual app
headless via Pilot to verify it mounts and wires up the new dependency table,
cache column, and depth toggle.
"""

import asyncio
import textwrap
from pathlib import Path

import pytest

import mutmut
import mutmut.ui.browse as browse
from mutmut.__main__ import _run
from mutmut.__main__ import apply_mutant
from mutmut.__main__ import get_diff_for_mutant
from mutmut.configuration import reset_config
from tests.e2e.e2e_utils import change_cwd


def _write_project(root: Path) -> None:
    (root / "src" / "calc").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "calc" / "__init__.py").write_text(
        textwrap.dedent(
            """
            def add(a, b):
                return a + b

            def double(x):
                return add(x, x)

            def untested(x):
                return x - 1
            """
        ).lstrip()
    )
    (root / "tests" / "test_calc.py").write_text(
        textwrap.dedent(
            """
            from calc import add, double

            def test_add():
                assert add(1, 2) == 3

            def test_double():
                assert double(4) == 8
            """
        ).lstrip()
    )
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            name = "calc"
            version = "0.1.0"
            requires-python = ">=3.10"

            [tool.mutmut]
            track_dependencies = true

            [tool.pytest.ini_options]
            asyncio_default_fixture_loop_scope = "function"
            """
        ).lstrip()
    )


def test_browser_mounts_with_dependency_and_cache_ui(tmp_path: Path):
    project = tmp_path / "calc_proj"
    project.mkdir()
    _write_project(project)

    captured: dict = {}

    def fake_runner(app):
        async def drive():
            async with app.run_test() as pilot:
                await pilot.pause()
                files = app.query_one("#files")
                deps = app.query_one("#dependencies")
                captured["files_rows"] = files.row_count
                captured["cache_col"] = "cache" in [k.value for k in files.columns]
                captured["deps_cols"] = len(deps.columns)

                app.set_focus(files)
                await pilot.pause()
                captured["mutants_rows"] = app.query_one("#mutants").row_count

                # The depth toggle must not raise.
                await pilot.press("v")
                await pilot.pause()
                captured["ok"] = True

        asyncio.run(drive())

    with change_cwd(project):
        mutmut._reset_globals()
        reset_config()
        _run([], None)

        original = browse._run_browser_app
        browse._run_browser_app = fake_runner
        try:
            browse.run_result_browser(
                show_killed=True,
                get_diff_for_mutant=get_diff_for_mutant,
                apply_mutant=apply_mutant,
            )
        finally:
            browse._run_browser_app = original

    assert captured.get("ok"), "browser did not mount"
    assert captured["files_rows"] > 0
    assert captured["cache_col"], "files table missing the cache column"
    assert captured["deps_cols"] == 2, "dependencies table should have upstream + downstream columns"
    assert captured["mutants_rows"] > 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
