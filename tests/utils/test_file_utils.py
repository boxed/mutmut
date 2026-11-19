from pathlib import Path
from types import SimpleNamespace

import pytest

import mutmut.utils.file_utils
from mutmut.utils.file_utils import copy_also_copy_files


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = SimpleNamespace(also_copy=[Path("tests/")], source_paths=[Path("src")])
    monkeypatch.setattr(mutmut.utils.file_utils, "config", lambda: cfg)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a(): pass\n")
    (tmp_path / "tests" / "test_b.py").write_text("def test_b(): pass\n")
    (tmp_path / "mutants").mkdir()
    return cfg


def test_deleted_test_file_is_removed_from_mutants(project):
    copy_also_copy_files()
    assert Path("mutants/tests/test_b.py").exists()

    Path("tests/test_b.py").unlink()
    copy_also_copy_files()

    assert Path("mutants/tests/test_a.py").exists()
    assert not Path("mutants/tests/test_b.py").exists()


def test_deleted_test_directory_is_removed_from_mutants(project):
    Path("tests/sub").mkdir()
    Path("tests/sub/test_c.py").write_text("def test_c(): pass\n")
    copy_also_copy_files()
    Path("mutants/tests/sub/__pycache__").mkdir()
    Path("mutants/tests/sub/__pycache__/test_c.cpython-313.pyc").write_bytes(b"")

    Path("tests/sub/test_c.py").unlink()
    Path("tests/sub").rmdir()
    copy_also_copy_files()

    assert not Path("mutants/tests/sub").exists()
    assert Path("mutants/tests/test_a.py").exists()


def test_pycache_of_existing_directory_is_kept(project):
    copy_also_copy_files()
    cached = Path("mutants/tests/__pycache__/test_a.cpython-313-pytest-9.0.0.pyc")
    cached.parent.mkdir()
    cached.write_bytes(b"")

    copy_also_copy_files()

    assert cached.exists()


def test_also_copy_overlapping_a_source_path_is_not_pruned(project):
    project.also_copy = [Path("src/")]
    Path("src").mkdir()
    Path("src/mod.py").write_text("x = 1\n")
    generated = Path("mutants/src/mod.py.meta")
    generated.parent.mkdir(parents=True)
    generated.write_text("{}")

    copy_also_copy_files()

    assert generated.exists()
