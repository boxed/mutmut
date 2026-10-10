import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import mutmut.utils.file_utils as file_utils
from mutmut.utils.file_utils import copy_also_copy_files
from mutmut.utils.file_utils import copy_src_dir


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project with a dangling link and a valid relative link under both a test dir and a source dir.

    Regression tests for #582: mutmut crashed when copying a dangling symlink into ``mutants/``.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "real.txt").write_text("data\n")
    for folder in ("tests/fixtures", "src/pkg"):
        (tmp_path / folder).mkdir(parents=True)
        os.symlink("missing-target", tmp_path / folder / "dangling")
        os.symlink("../../shared/real.txt", tmp_path / folder / "rel_valid")
    (tmp_path / "src" / "pkg" / "__init__.py").write_text("")
    monkeypatch.setattr(
        file_utils, "config", lambda: SimpleNamespace(source_paths=[Path("src")], also_copy=[Path("tests")])
    )
    return tmp_path


def _assert_dangling_link_kept(path: Path) -> None:
    assert path.is_symlink()
    assert os.readlink(path) == "missing-target"
    assert not path.exists()


def _assert_copied_as_file(path: Path) -> None:
    # Valid links are followed, so the copy keeps working inside mutants/ even when
    # the relative target lives outside the copied directory.
    assert not path.is_symlink()
    assert path.read_text() == "data\n"


def test_copy_also_copy_files_keeps_dangling_symlink(project):
    copy_also_copy_files()

    _assert_dangling_link_kept(project / "mutants" / "tests" / "fixtures" / "dangling")
    _assert_copied_as_file(project / "mutants" / "tests" / "fixtures" / "rel_valid")


def test_copy_src_dir_keeps_dangling_symlink(project):
    copy_src_dir()

    _assert_dangling_link_kept(project / "mutants" / "src" / "pkg" / "dangling")
    _assert_copied_as_file(project / "mutants" / "src" / "pkg" / "rel_valid")


def test_copies_can_be_repeated_with_dangling_symlinks(project):
    # mutmut copies on every run; a dangling link left in mutants/ must not break the next run.
    for _ in range(2):
        copy_also_copy_files()
        copy_src_dir()

    _assert_dangling_link_kept(project / "mutants" / "tests" / "fixtures" / "dangling")
    _assert_dangling_link_kept(project / "mutants" / "src" / "pkg" / "dangling")
