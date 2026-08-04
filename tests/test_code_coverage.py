import coverage

from mutmut.code_coverage import _excluded_lines
from mutmut.code_coverage import get_excluded_lines_for_file


def test_get_excluded_lines_for_file_without_data():
    assert get_excluded_lines_for_file("foo.py", None) == set()


def test_get_excluded_lines_for_file_unknown_file():
    assert get_excluded_lines_for_file("foo.py", {}) == set()


def test_excluded_lines_of_unreadable_file(tmp_path):
    assert _excluded_lines(coverage.Coverage(data_file=None), str(tmp_path / "does_not_exist.py")) == set()


def test_excluded_lines_reports_only_the_first_line_of_each_statement(tmp_path):
    # coverage.py only reports the line a statement *starts* on, which is why the
    # excluded lines have to be expanded to full statements before they are of any use.
    # If that ever changes, the expansion is doing unnecessary work.
    source_file = tmp_path / "excluded.py"
    source_file.write_text(
        "def keep(a, b):\n"
        "    return (\n"
        "        a\n"
        "        + b\n"
        "    )\n"
        "\n"
        "def drop(a, b):  # pragma: no cover\n"
        "    return (\n"
        "        a\n"
        "        + b\n"
        "    )\n"
    )

    excluded = _excluded_lines(coverage.Coverage(data_file=None), str(source_file))

    assert excluded == {7, 8}


def test_excluded_lines_honours_the_projects_coverage_config(tmp_path, monkeypatch):
    (tmp_path / ".coveragerc").write_text("[report]\nexclude_also =\n    if not_tested:\n")
    source_file = tmp_path / "configured.py"
    source_file.write_text("def foo(not_tested):\n    if not_tested:\n        return 1 + 1\n    return 2 + 2\n")

    monkeypatch.chdir(tmp_path)
    excluded = _excluded_lines(coverage.Coverage(data_file=None), str(source_file))

    assert excluded == {2, 3}
