from pathlib import Path

import pytest

import nootnoot.app.mutation as nootnoot_mutation
from nootnoot.app.mutation import InvalidGeneratedSyntaxException, create_mutants

source_dir = Path(__file__).parent / "data" / "test_generation"
source_dir = source_dir.relative_to(Path.cwd())


class MockConfig:
    def should_ignore_for_mutation(self, path: Path) -> bool:
        return False


def test_mutant_generation_raises_exception_on_invalid_syntax(nootnoot_state, monkeypatch):
    nootnoot_state.config = MockConfig()

    source_files = [
        source_dir / "valid_syntax_1.py",
        source_dir / "valid_syntax_2.py",
        source_dir / "valid_syntax_3.py",
        source_dir / "valid_syntax_4.py",
        source_dir / "invalid_syntax.py",
    ]
    monkeypatch.setattr(nootnoot_mutation, "walk_source_files", lambda _state: source_files)

    # should raise an exception, because we copy the invalid_syntax.py file and then verify
    # if it is valid syntax
    with pytest.raises(InvalidGeneratedSyntaxException) as excinfo, pytest.warns(SyntaxWarning):
        create_mutants(max_children=2, state=nootnoot_state)
    assert "invalid_syntax.py" in str(excinfo.value)
