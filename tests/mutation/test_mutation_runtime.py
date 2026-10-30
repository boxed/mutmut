"""Runtime integration tests that use exec() to verify mutated code works at runtime.

These tests sit between unit tests and E2E tests: they generate mutated code
via mutate_file_contents and then exec() it to verify runtime behavior.
"""

from mutmut.mutation.file_mutation import mutate_file_contents


def test_enum_mutation_runtime_execution(monkeypatch):
    """Test that mutated enum code can actually be executed and mutants activated."""
    source = """
from enum import Enum

class Color(Enum):
    RED = 1
    GREEN = 2

    def describe(self):
        return self.name.lower()
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    assert len(mutant_names) > 0, "Should have at least one mutant"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    Color = namespace["Color"]

    assert Color.RED.value == 1
    assert Color.GREEN.value == 2

    assert Color.RED.describe() == "red"

    mutant_name = "test_module." + mutant_names[0]
    monkeypatch.setenv("MUTANT_UNDER_TEST", mutant_name)


def test_enum_creation_hooks_runtime_execution(monkeypatch):
    """Test that an enum whose __init__ and _generate_next_value_ run during class creation can be executed."""
    source = """
from enum import Enum, auto

class Color(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return count + 10

    RED = auto()
    GREEN = auto()

    def __init__(self, value):
        self.label = f"c{value}"

    def describe(self):
        return self.name.lower()
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    assert len(mutant_names) > 0, "Should have at least one mutant"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    Color = namespace["Color"]

    assert Color.GREEN.value == 11
    assert Color.GREEN.label == "c11"
    assert Color.GREEN.describe() == "green"


def test_type_annotation_runtime_execution(monkeypatch):
    """Test that forward and quoted annotations can be executed

    We don't really care about any mutations, we just care if the annotations are processed properly.
    """
    source = """
from enum import Enum
from typing import List, Literal

class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3

    def describe(self) -> Literal[ "red", 'green', \"""blue\""" ]: # worst case type annotation
        return self.name.lower()

    @classmethod
    def from_name(cls, name: str) -> "Color":
        name = name.upper()
        vals = {
            Color.RED.name: Color.RED,
            Color.GREEN.name: Color.GREEN,
            Color.BLUE.name: Color.BLUE
        }
        return vals[name]
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    assert len(mutant_names) > 0, "Should have at least one mutant"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    Color = namespace["Color"]

    assert Color.RED.value == 1
    assert Color.RED.describe() == "red"

    assert Color.from_name("green") == Color.GREEN


def test_regular_class_staticmethod_runtime(monkeypatch):
    """Test that staticmethod mutation in regular classes works at runtime."""
    source = """
class Calculator:
    @staticmethod
    def add(a, b):
        return a + b
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    assert len(mutant_names) > 0, "Should have at least one mutant"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    Calculator = namespace["Calculator"]

    assert Calculator.add(2, 3) == 5

    mutant_name = "test_module." + mutant_names[0]
    monkeypatch.setenv("MUTANT_UNDER_TEST", mutant_name)

    assert Calculator.add(5, 3) == 2


def test_classmethod_subclass_runtime(monkeypatch):
    """Test that a @classmethod works at runtime"""
    source = """
class Base:
    @classmethod
    def create(cls):
        return cls(1)

class SubClass(Base):
    def __init__(self, value):
        self.value = value
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    assert len(mutant_names) > 0, "Should have at least one mutant"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    SubClass = namespace["SubClass"]

    assert SubClass.create().value == 1

    mutant_name = "test_module." + mutant_names[0]
    monkeypatch.setenv("MUTANT_UNDER_TEST", mutant_name)

    assert SubClass.create().value is None


def test_default_arg_mutation(monkeypatch):
    """Test that simple default arguments are mutated"""
    source = """
def foo(a: int, b: int = 2):
    return a + b
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    assert len(mutant_names) > 0, "Should have at least one mutant"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    foo = namespace["foo"]

    assert foo(1) == 3
    assert foo(1, 10) == 11

    mutant_name = "test_module." + mutant_names[0]
    monkeypatch.setenv("MUTANT_UNDER_TEST", mutant_name)

    assert foo(1) == 4
    assert foo(1, 10) == 11


def test_override_classmethod_subclass_runtime(monkeypatch):
    """A @classmethod stacked with @override still binds to the subclass, and keeps its override marker"""
    source = """
from typing_extensions import override

class Base:
    @classmethod
    def create(cls):
        return cls(0)

class Child(Base):
    def __init__(self, value):
        self.value = value

    @classmethod
    @override
    def create(cls):
        return cls(1)

class GrandChild(Child):
    pass
""".strip()

    mutated_file = mutate_file_contents("test.py", source)
    mutated_code, mutant_names = mutated_file.code, mutated_file.mutant_names
    child_mutants = [name for name in mutant_names if name.startswith("xǁChildǁcreate__mutmut")]
    assert len(child_mutants) > 0, "Should have at least one mutant of the override"

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_code, namespace)
    GrandChild = namespace["GrandChild"]

    created = GrandChild.create()
    assert type(created) is GrandChild
    assert created.value == 1
    assert namespace["Child"].__dict__["create"].__func__.__override__ is True

    monkeypatch.setenv("MUTANT_UNDER_TEST", "test_module." + child_mutants[0])

    assert GrandChild.create().value is None
