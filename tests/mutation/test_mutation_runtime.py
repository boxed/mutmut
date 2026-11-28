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


GUARDED_METACLASS_SOURCE = """
class _Guarded(type):
    def __getattribute__(cls, name):
        if not name.startswith("__"):
            raise RuntimeError(f"{name} is deprecated")
        return super().__getattribute__(name)


class Catalog(metaclass=_Guarded):
    def __init__(self, value):
        self.value = value + 1

    @classmethod
    def create(cls, value):
        return cls(value * 2)


class Child(Catalog):
    def describe(self):
        return f"child {self.value}"
""".strip()


def test_metaclass_getattribute_runtime_execution(monkeypatch):
    """
    Classes whose metaclass refuses reads of unknown attributes can be imported and run when mutated.

    pypdf's CatalogDictionary raises a DeprecationError for every attribute read through its metaclass,
    which made importing the mutated module fail. Child inherits the metaclass without naming it.
    """
    mutated_file = mutate_file_contents("test.py", GUARDED_METACLASS_SOURCE)
    assert "xǁCatalogǁcreate__mutmut_1" in mutated_file.mutant_names

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_file.code, namespace)
    Child = namespace["Child"]

    created = Child(0).create(3)

    assert type(created) is Child
    assert created.value == 7
    assert created.describe() == "child 7"


def test_metaclass_getattribute_classmethod_mutant_activation(monkeypatch):
    """
    A mutant of a classmethod can be activated on a class whose metaclass refuses reads of unknown attributes.

    The trampoline of a classmethod looks the method up on the class it was called on (here the
    subclass Child), which must not go through the __getattribute__ of the metaclass.
    """
    mutated_file = mutate_file_contents("test.py", GUARDED_METACLASS_SOURCE)
    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_file.code, namespace)
    Child = namespace["Child"]
    child = Child(0)

    # mutant 2 turns `value * 2` into `value / 2`
    monkeypatch.setenv("MUTANT_UNDER_TEST", "test_module.xǁCatalogǁcreate__mutmut_2")
    created = child.create(3)

    assert type(created) is Child
    assert created.value == 2.5


def test_class_replaced_by_decorator_import(monkeypatch):
    """
    A mutated module still imports when a class decorator replaces the class with an instance.

    The generated methods are then read from the instance, as before reading them
    without the metaclass. Calling such a method is a different problem and is not checked here.
    """
    source = """
def singleton(cls):
    return cls()


@singleton
class Config:
    def get(self):
        return 1 + 1
""".strip()
    mutated_file = mutate_file_contents("test.py", source)
    assert "xǁConfigǁget__mutmut_1" in mutated_file.mutant_names

    monkeypatch.setenv("MUTANT_UNDER_TEST", "none")
    namespace = {"__name__": "test_module"}
    exec(mutated_file.code, namespace)

    assert type(namespace["Config"]).__name__ == "Config"


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
