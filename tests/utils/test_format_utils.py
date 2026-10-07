from pathlib import Path

import pytest

from mutmut.configuration import reset_config
from mutmut.utils.format_utils import get_mutant_name


@pytest.fixture(autouse=True)
def _reset_config_singleton():
    reset_config()
    yield
    reset_config()


@pytest.fixture
def in_tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.mutmut]\n")
    return tmp_path


def test_default_still_strips_src_prefix(in_tmp_dir: Path):
    """src-layout default: the container dir is not part of the import name."""
    assert get_mutant_name(Path("src/my_lib/__init__.py"), "x_hello__mutmut_1") == "my_lib.x_hello__mutmut_1"


def test_flat_src_layout_keeps_prefix(in_tmp_dir: Path):
    """strip_src_prefix = false: `src` IS the import package, so mutant names
    must keep the `src.` prefix — the trampoline routing compares them against
    the imported module's `__module__`."""
    (in_tmp_dir / "pyproject.toml").write_text("[tool.mutmut]\nstrip_src_prefix = false\n")
    reset_config()
    assert get_mutant_name(Path("src/calc.py"), "x_add__mutmut_1") == "src.calc.x_add__mutmut_1"
