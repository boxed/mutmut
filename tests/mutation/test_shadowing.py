"""Tests for shadowing: a surviving mutant that removes code hides the mutants inside that code."""

from pathlib import Path

import pytest
from textual.app import App

from mutmut.mutation.data import SourceFileMutationData
from mutmut.mutation.data import SourceSpan
from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.ui.browse import run_result_browser
from mutmut.utils.format_utils import get_mutant_name

SOURCE = """\
def foo(a):
    x = bar(a + 1)
    return x - 1
"""


def code_at(span: SourceSpan) -> str:
    lines = SOURCE.splitlines()[span.start_line - 1 : span.end_line]
    lines[-1] = lines[-1][: span.end_column]
    lines[0] = lines[0][span.start_column :]
    return "\n".join(lines)


def test_mutants_record_the_code_they_change_and_remove():
    mutated_file = mutate_file_contents("test.py", SOURCE)

    assert {name: code_at(span) for name, span in mutated_file.source_span_by_mutant_name.items()} == {
        "x_foo__mutmut_1": "x = bar(a + 1)",  # x = None
        "x_foo__mutmut_2": "bar(a + 1)",  # bar(None)
        "x_foo__mutmut_3": "a + 1",  # a - 1
        "x_foo__mutmut_4": "1",  # a + 2
        "x_foo__mutmut_5": "x - 1",  # x + 1
        "x_foo__mutmut_6": "1",  # x - 2
    }
    assert {name: code_at(span) for name, span in mutated_file.removed_span_by_mutant_name.items()} == {
        "x_foo__mutmut_1": "bar(a + 1)",
        "x_foo__mutmut_2": "a + 1",
    }


def write_project(exit_codes: list[int | None], source: str = SOURCE) -> None:
    """Set up a project for `source` the way `mutmut run` leaves it, with the given results."""
    Path("pyproject.toml").write_text('[tool.mutmut]\nsource_paths = ["test.py"]\n')
    Path("test.py").write_text(source)
    mutated_file = mutate_file_contents("test.py", source)
    Path("mutants").mkdir(exist_ok=True)
    Path("mutants/test.py").write_text(mutated_file.code)

    data = SourceFileMutationData(path="test.py")
    names = [get_mutant_name(Path("test.py"), name) for name in mutated_file.mutant_names]
    data.exit_code_by_key = dict(zip(names, exit_codes, strict=True))
    data.source_span_by_key = {
        get_mutant_name(Path("test.py"), name): span for name, span in mutated_file.source_span_by_mutant_name.items()
    }
    data.removed_span_by_key = {
        get_mutant_name(Path("test.py"), name): span for name, span in mutated_file.removed_span_by_mutant_name.items()
    }
    data.save()


@pytest.mark.parametrize(
    "exit_codes, expected",
    [
        pytest.param(
            [0, 0, 0, 0, 0, 0],
            {"test.x_foo__mutmut_2": 1, "test.x_foo__mutmut_3": 1, "test.x_foo__mutmut_4": 1},
            id="outermost survivor shadows",
        ),
        pytest.param(
            [1, 0, 0, 0, 0, 0],
            {"test.x_foo__mutmut_3": 2, "test.x_foo__mutmut_4": 2},
            id="killed mutant does not shadow",
        ),
        pytest.param([1, 1, 0, 0, 0, 0], {}, id="nothing shadows"),
        pytest.param([None] * 6, {}, id="not checked yet"),
    ],
)
def test_shadowed_by_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_codes, expected):
    monkeypatch.chdir(tmp_path)
    write_project(exit_codes)

    data = SourceFileMutationData(path="test.py")
    data.load()

    assert data.shadowed_by_key() == {key: f"test.x_foo__mutmut_{n}" for key, n in expected.items()}


@pytest.mark.parametrize(
    "source, mutant_count",
    [
        pytest.param("def foo():\n    x = False\n", 2, id="name"),
        pytest.param("def foo():\n    x = 1\n", 2, id="number"),
        pytest.param("def foo(x):\n    return fmt(x, upper=False)\n", 5, id="arguments"),
    ],
)
def test_replacing_a_name_or_literal_does_not_shadow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, mutant_count: int
):
    """`x = False` -> `x = None` almost always survives, and must not hide `x = False` -> `x = True`."""
    monkeypatch.chdir(tmp_path)
    write_project([0] * mutant_count, source)

    data = SourceFileMutationData(path="test.py")
    data.load()

    assert data.removed_span_by_key == {}
    assert data.shadowed_by_key() == {}


@pytest.mark.asyncio
async def test_browse_hides_shadowed_mutants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    write_project([0, 0, 0, 1, 0, 1])

    apps: list[App[None]] = []
    monkeypatch.setattr(App, "run", lambda self: apps.append(self))
    run_result_browser(show_killed=False)
    [app] = apps

    def listed_mutants() -> list[str]:
        mutants_table = app.query_one("#mutants")
        return [mutants_table.get_row_at(i)[0] for i in range(mutants_table.row_count)]  # type: ignore[attr-defined]

    async with app.run_test() as pilot:
        await pilot.pause()
        assert listed_mutants() == ["test.x_foo__mutmut_1", "test.x_foo__mutmut_5"]

        await pilot.press("s")
        assert listed_mutants() == [
            "test.x_foo__mutmut_1",
            "test.x_foo__mutmut_2",
            "test.x_foo__mutmut_3",
            "test.x_foo__mutmut_5",
        ]

        await pilot.press("s")
        assert listed_mutants() == ["test.x_foo__mutmut_1", "test.x_foo__mutmut_5"]
