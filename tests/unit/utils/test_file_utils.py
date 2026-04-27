"""Tests for mutmut.utils.file_utils module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from mutmut.utils.file_utils import copy_also_copy_files
from mutmut.utils.file_utils import copy_src_dir
from mutmut.utils.file_utils import setup_source_paths
from mutmut.utils.file_utils import walk_all_files
from mutmut.utils.file_utils import walk_source_files


class TestWalkAllFiles:
    """Tests for walk_all_files function."""

    def test_walks_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test walking a directory yields all files."""
        # Create test structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "module.py").write_text("# code")
        (tmp_path / "src" / "data.txt").write_text("data")
        (tmp_path / "src" / "subdir").mkdir()
        (tmp_path / "src" / "subdir" / "nested.py").write_text("# nested")

        mock_config = MagicMock()
        mock_config.source_paths = [str(tmp_path / "src")]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            files = list(walk_all_files())

        filenames = [f[1] for f in files]
        assert "module.py" in filenames
        assert "data.txt" in filenames
        assert "nested.py" in filenames

    def test_walks_single_file(self, tmp_path: Path) -> None:
        """Test walking a single file path."""
        test_file = tmp_path / "single.py"
        test_file.write_text("# single file")

        mock_config = MagicMock()
        mock_config.source_paths = [str(test_file)]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            files = list(walk_all_files())

        assert len(files) == 1
        assert files[0] == ("", str(test_file))


class TestWalkSourceFiles:
    """Tests for walk_source_files function."""

    def test_filters_python_files_only(self, tmp_path: Path) -> None:
        """Test that only .py files are yielded."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "module.py").write_text("# code")
        (tmp_path / "src" / "data.txt").write_text("data")
        (tmp_path / "src" / "config.json").write_text("{}")

        mock_config = MagicMock()
        mock_config.source_paths = [str(tmp_path / "src")]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            files = list(walk_source_files())

        assert len(files) == 1
        assert files[0].name == "module.py"

    def test_returns_path_objects(self, tmp_path: Path) -> None:
        """Test that Path objects are returned."""
        (tmp_path / "test.py").write_text("# test")

        mock_config = MagicMock()
        mock_config.source_paths = [str(tmp_path)]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            files = list(walk_source_files())

        assert all(isinstance(f, Path) for f in files)


class TestCopySrcDir:
    """Tests for copy_src_dir function."""

    def test_copies_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test copying a source directory to mutants/."""
        monkeypatch.chdir(tmp_path)

        # Create source structure using relative paths (like real usage)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "module.py").write_text("# code")
        (tmp_path / "src" / "subdir").mkdir()
        (tmp_path / "src" / "subdir" / "nested.py").write_text("# nested")

        mock_config = MagicMock()
        mock_config.source_paths = ["src"]  # Relative path

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            copy_src_dir()

        assert (tmp_path / "mutants" / "src" / "module.py").exists()
        assert (tmp_path / "mutants" / "src" / "subdir" / "nested.py").exists()

    def test_copies_single_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test copying a single file to mutants/."""
        monkeypatch.chdir(tmp_path)

        test_file = tmp_path / "single.py"
        test_file.write_text("# single file")

        mock_config = MagicMock()
        mock_config.source_paths = ["single.py"]  # Relative path

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            copy_src_dir()

        assert (tmp_path / "mutants" / "single.py").exists()


class TestCopyAlsoCopyFiles:
    """Tests for copy_also_copy_files function."""

    def test_copies_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
        """Test copying a single file from also_copy config."""
        monkeypatch.chdir(tmp_path)

        # Create file to copy
        (tmp_path / "config.ini").write_text("[settings]")
        (tmp_path / "mutants").mkdir()

        mock_config = MagicMock()
        mock_config.also_copy = ["config.ini"]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            copy_also_copy_files()

        assert (tmp_path / "mutants" / "config.ini").exists()
        captured = capsys.readouterr()
        assert "also copying" in captured.out

    def test_copies_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test copying a directory from also_copy config."""
        monkeypatch.chdir(tmp_path)

        # Create directory to copy
        (tmp_path / "fixtures").mkdir()
        (tmp_path / "fixtures" / "data.json").write_text("{}")
        (tmp_path / "mutants").mkdir()

        mock_config = MagicMock()
        mock_config.also_copy = ["fixtures"]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            copy_also_copy_files()

        assert (tmp_path / "mutants" / "fixtures" / "data.json").exists()

    def test_skips_nonexistent_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that nonexistent paths are skipped without error."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "mutants").mkdir()

        mock_config = MagicMock()
        mock_config.also_copy = ["nonexistent_file.txt"]

        with patch("mutmut.utils.file_utils.config", return_value=mock_config):
            # Should not raise
            copy_also_copy_files()


class TestSetupSourcePaths:
    """Tests for setup_source_paths function."""

    def test_adds_mutants_to_sys_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that mutants directories are added to sys.path."""
        monkeypatch.chdir(tmp_path)

        # Create mutants/src directory
        (tmp_path / "mutants" / "src").mkdir(parents=True)

        original_path = sys.path.copy()

        try:
            setup_source_paths()
            # Check that mutants/src was added to the front of sys.path
            assert str((tmp_path / "mutants" / "src").absolute()) in sys.path
        finally:
            sys.path[:] = original_path

    def test_removes_original_source_from_sys_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that original source paths are removed from sys.path."""
        monkeypatch.chdir(tmp_path)

        # Create mutants directory
        (tmp_path / "mutants" / "src").mkdir(parents=True)

        # Add the original src to sys.path
        original_path = sys.path.copy()
        src_path = str(tmp_path / "src")
        (tmp_path / "src").mkdir()
        sys.path.insert(0, src_path)

        try:
            setup_source_paths()
            # The resolved path should be removed
            resolved_paths = [str(Path(p).resolve()) for p in sys.path]
            assert str((tmp_path / "src").resolve()) not in resolved_paths
        finally:
            sys.path[:] = original_path
