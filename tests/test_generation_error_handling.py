from pathlib import Path

import pytest

import mutmut
import mutmut.mutation as mutmut_mutation
from mutmut.mutation import InvalidGeneratedSyntaxException, create_mutants

source_dir = Path(__file__).parent / "data" / "test_generation"
source_dir = source_dir.relative_to(Path.cwd())


class MockConfig:
    def should_ignore_for_mutation(self, path: Path) -> bool:
        return False


def test_mutant_generation_raises_exception_on_invalid_syntax(monkeypatch):
    mutmut._reset_globals()
    mutmut.config = MockConfig()

    source_files = [
        source_dir / "valid_syntax_1.py",
        source_dir / "valid_syntax_2.py",
        source_dir / "valid_syntax_3.py",
        source_dir / "valid_syntax_4.py",
        source_dir / "invalid_syntax.py",
    ]
    monkeypatch.setattr(mutmut_mutation, "walk_source_files", lambda: source_files)
    monkeypatch.setattr("mutmut.config.should_ignore_for_mutation", lambda _path: False)

    # should raise an exception, because we copy the invalid_syntax.py file and then verify
    # if it is valid syntax
    with pytest.raises(InvalidGeneratedSyntaxException) as excinfo, pytest.warns(SyntaxWarning):
        create_mutants(max_children=2)
    assert "invalid_syntax.py" in str(excinfo.value)
