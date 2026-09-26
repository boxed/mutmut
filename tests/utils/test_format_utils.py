import types

import pytest

import mutmut
from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.utils.format_utils import is_mutmut_generated_name

SOURCE = '''
from dataclasses import dataclass


@dataclass
class DateRange:
    """A closed date interval."""

    start: int
    end: int

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError("end before start")

    def length(self):
        """Number of days in the range."""
        return self.end - self.start + 1


def span(r):
    """Length of the range."""
    return r.end - r.start + 1
'''


def _load_mutated_module() -> types.ModuleType:
    module = types.ModuleType("demo")
    exec(compile(mutate_file_contents("demo.py", SOURCE).code, "demo.py", "exec"), module.__dict__)
    return module


def _public(namespace: dict[str, object]) -> set[str]:
    return {name for name in namespace if not name.startswith("_")}


def test_is_mutmut_generated_name_is_public_api():
    assert mutmut.is_mutmut_generated_name is is_mutmut_generated_name


def test_filters_every_generated_class_member():
    module = _load_mutated_module()

    public_members = _public(vars(module.DateRange))
    assert any(is_mutmut_generated_name(name) for name in public_members), "precondition: mutmut adds members"
    assert {name for name in public_members if not is_mutmut_generated_name(name)} == {"length"}


def test_filters_every_generated_module_attribute():
    module = _load_mutated_module()

    public_names = _public(vars(module))
    assert {name for name in public_names if not is_mutmut_generated_name(name)} == {
        "DateRange",
        "MutantDict",
        "dataclass",
        "span",
    }


@pytest.mark.parametrize(
    "name",
    [
        "length",
        "span",
        "x",
        "x_",
        "xǁ",
        "x_value",
        "mutants",
        "mutants_x",
        "mutants_count",
        "mutmut_orig",
        "__post_init__",
    ],
)
def test_does_not_match_user_names(name):
    assert not is_mutmut_generated_name(name)
