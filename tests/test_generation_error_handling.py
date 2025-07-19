from pathlib import Path
from mutmut.__main__ import create_mutants, Config, InvalidGeneratedSyntaxException
import mutmut.__main__
import mutmut
import pytest
import os

source_dir = Path(__file__).parent / 'data' / 'test_generation'
source_dir = source_dir.relative_to(os.getcwd())

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
    monkeypatch.setattr(mutmut.__main__, "walk_source_files", lambda: source_files)
    monkeypatch.setattr("mutmut.config.should_ignore_for_mutation", lambda _path: False)

    # should raise an exception, because we copy the invalid_syntax.py file and then verify
    # if it is valid syntax
    with pytest.raises(InvalidGeneratedSyntaxException) as excinfo:
        # should raise a warning, because libcst is not able to parse invalid_syntax.py
        with pytest.warns(SyntaxWarning):
            create_mutants(max_children=2)
    assert 'invalid_syntax.py' in str(excinfo.value)
