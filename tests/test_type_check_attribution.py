"""Attributing type errors to mutants, and running the type checker in the background."""

import json
import sys
from pathlib import Path

import pytest

import mutmut.mutation.file_mutation
from mutmut.mutation.data import LineSpan
from mutmut.mutation.data import MutantLineSpans
from mutmut.mutation.file_mutation import MutatedMethodLocation
from mutmut.mutation.file_mutation import filter_mutants_with_type_checker
from mutmut.mutation.file_mutation import find_method_at_line
from mutmut.mutation.file_mutation import load_line_spans_index
from mutmut.mutation.file_mutation import mutated_method_locations
from mutmut.type_checking import TypeCheckerProcess
from mutmut.type_checking import TypeCheckingError
from mutmut.type_checking import start_type_checker

MUTATED_SOURCE = (
    "from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict\n"
    "\n"
    "def helper(value):\n"
    "    return value\n"
    "\n"
    "def x_mutate_me__mutmut_orig():\n"
    "    return 1\n"
    "\n"
    "def x_mutate_me__mutmut_1():\n"
    "    return 2\n"
    "\n"
    "def x_mutate_me__mutmut_2():\n"
    "    return None\n"
)


def _write_spans(mutated_file: Path, spans: dict[str, tuple[int, int]], version: int = 1) -> None:
    Path(str(mutated_file) + ".spans").write_text(json.dumps({"version": version, "spans": spans}))


class TestLoadLineSpansIndex:
    def test_reads_the_index_written_at_generation(self, tmp_path):
        mutated_file = tmp_path / "module.py"
        mutated_file.write_text(MUTATED_SOURCE)
        _write_spans(mutated_file, {"x_mutate_me__mutmut_1": (9, 10)})

        assert load_line_spans_index(mutated_file) == {"x_mutate_me__mutmut_1": LineSpan(9, 10)}

    def test_missing_or_unknown_index_means_none(self, tmp_path):
        mutated_file = tmp_path / "module.py"
        mutated_file.write_text(MUTATED_SOURCE)
        assert load_line_spans_index(mutated_file) is None

        _write_spans(mutated_file, {"x_mutate_me__mutmut_1": (9, 10)}, version=MutantLineSpans.format_version + 1)
        assert load_line_spans_index(mutated_file) is None

        Path(str(mutated_file) + ".spans").write_text("{not json")
        assert load_line_spans_index(mutated_file) is None


class TestMutatedMethodLocations:
    def test_uses_the_index_without_parsing_the_file(self, tmp_path):
        mutated_file = tmp_path / "module.py"
        mutated_file.write_text("this is not python (")
        _write_spans(mutated_file, {"x_b__mutmut_1": (20, 25), "x_a__mutmut_orig": (5, 8)})

        assert mutated_method_locations(mutated_file) == [
            MutatedMethodLocation(mutated_file, "x_a__mutmut_orig", 5, 8),
            MutatedMethodLocation(mutated_file, "x_b__mutmut_1", 20, 25),
        ]

    def test_parses_the_file_when_there_is_no_index(self, tmp_path):
        mutated_file = tmp_path / "module.py"
        mutated_file.write_text(MUTATED_SOURCE)

        assert mutated_method_locations(mutated_file) == [
            MutatedMethodLocation(mutated_file, "x_mutate_me__mutmut_orig", 6, 7),
            MutatedMethodLocation(mutated_file, "x_mutate_me__mutmut_1", 9, 10),
            MutatedMethodLocation(mutated_file, "x_mutate_me__mutmut_2", 12, 13),
        ]


def test_find_method_at_line_uses_the_sorted_start_lines():
    locations = [
        MutatedMethodLocation(Path("m.py"), "x_a__mutmut_1", 5, 8),
        MutatedMethodLocation(Path("m.py"), "x_a__mutmut_2", 20, 25),
    ]
    sorted_starts = [5, 20]

    assert find_method_at_line(locations, sorted_starts, 4) is None
    assert find_method_at_line(locations, sorted_starts, 5) == locations[0]
    assert find_method_at_line(locations, sorted_starts, 8) == locations[0]
    assert find_method_at_line(locations, sorted_starts, 9) is None
    assert find_method_at_line(locations, sorted_starts, 25) == locations[1]
    assert find_method_at_line(locations, sorted_starts, 26) is None


class _FinishedChecker:
    """Stands in for a TypeCheckerProcess whose report is already known."""

    def __init__(self, errors: list[TypeCheckingError]) -> None:
        self.errors = errors

    def result(self) -> list[TypeCheckingError]:
        return self.errors


def test_filter_attributes_errors_from_a_background_checker_via_the_index(tmp_path, monkeypatch):
    project = tmp_path
    mutated_file = project / "mutants" / "src" / "module.py"
    mutated_file.parent.mkdir(parents=True)
    mutated_file.write_text(MUTATED_SOURCE)
    _write_spans(
        mutated_file,
        {"x_mutate_me__mutmut_orig": (6, 7), "x_mutate_me__mutmut_1": (9, 10), "x_mutate_me__mutmut_2": (12, 13)},
    )
    errors = [
        TypeCheckingError(file_path=mutated_file, line_number=13, error_description="None is not an int"),
    ]
    monkeypatch.chdir(project)

    def must_not_run(command):
        raise AssertionError("the checker's report should be reused, not recomputed")

    monkeypatch.setattr(mutmut.mutation.file_mutation, "run_type_checker", must_not_run)

    caught = filter_mutants_with_type_checker(_FinishedChecker(errors))  # type: ignore[arg-type]

    # the "src" source directory is not part of the module name
    assert list(caught) == ["module.x_mutate_me__mutmut_2"]
    assert caught["module.x_mutate_me__mutmut_2"].error.error_description == "None is not an int"
    assert caught["module.x_mutate_me__mutmut_2"].method_location.line_number_start == 12


class TestTypeCheckerProcess:
    def test_runs_in_the_background_and_parses_the_report(self, tmp_path):
        report = {"generalDiagnostics": [{"file": "a.py", "range": {"start": {"line": 3}}, "message": "boom"}]}
        checker = start_type_checker(
            [sys.executable, "-c", f"import json; print(json.dumps({report!r}))"],
            cwd=tmp_path,
        )

        assert isinstance(checker, TypeCheckerProcess)
        assert checker.result() == [TypeCheckingError(file_path=Path("a.py"), line_number=4, error_description="boom")]

    def test_runs_with_the_given_working_directory(self, tmp_path):
        checker = start_type_checker(
            [
                sys.executable,
                "-c",
                'import json, os; print(json.dumps({"generalDiagnostics": [], "cwd": os.getcwd()}))',
            ],
            cwd=tmp_path,
        )
        checker.process.wait()
        checker._stdout.seek(0)
        assert json.loads(checker._stdout.read())["cwd"] == str(tmp_path.resolve())
        checker.terminate()

    def test_terminate_stops_a_running_checker(self):
        checker = start_type_checker([sys.executable, "-c", "import time; time.sleep(60)"])
        assert checker.process.poll() is None

        checker.terminate()

        assert checker.process.poll() is not None

    def test_non_json_output_is_reported_with_stderr(self):
        checker = start_type_checker(
            [sys.executable, "-c", "import sys; print('not json'); print('details', file=sys.stderr)"]
        )
        with pytest.raises(Exception, match=r"(?s)did not return JSON.*not json.*details"):
            checker.result()
