from pathlib import Path
from unittest.mock import Mock

import mutmut.__main__
from mutmut.__main__ import precompile_mutants
from mutmut.configuration import Config


def test_precompile_compiles_every_mutated_source_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    package = tmp_path / "mutants" / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "mod.py").write_text("def f():\n    return 1\n")
    (tmp_path / "mutants" / "single.py").write_text("x = 1\n")
    (tmp_path / "mutants" / "untouched.py").write_text("y = 1\n")

    cfg = Mock(spec=Config)
    cfg.source_paths = [Path("src"), Path("single.py"), Path("absent.py")]
    monkeypatch.setattr(mutmut.__main__, "config", lambda: cfg)

    precompile_mutants(max_children=2)

    assert list((package / "__pycache__").glob("mod.*.pyc"))
    assert list((tmp_path / "mutants" / "__pycache__").glob("single.*.pyc"))
    assert not list((tmp_path / "mutants" / "__pycache__").glob("untouched.*.pyc"))
