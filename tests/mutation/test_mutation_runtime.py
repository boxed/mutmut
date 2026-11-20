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


def _load(source, monkeypatch, mutant_of=None):
    """`source` mutated and executed, with the first mutant of the function `mutant_of` active, or none."""
    mutated_file = mutate_file_contents("test.py", source)
    of_it = [m for m in mutated_file.mutant_names if mutant_of is not None and f"{mutant_of}__mutmut_" in m]
    name = "test_module." + of_it[0] if of_it else "none"
    assert (mutant_of is None) or of_it, f"no mutant of {mutant_of}"
    monkeypatch.setenv("MUTANT_UNDER_TEST", name)
    namespace = {"__name__": "test_module"}
    exec(mutated_file.code, namespace)
    return namespace, mutated_file.mutant_names


def test_a_property_stays_a_property_and_its_mutants_run(monkeypatch):
    source = """
class Box:
    def __init__(self, a, b):
        self.a, self.b = a, b

    @property
    def total(self):
        return self.a + self.b
""".strip()

    namespace, mutants = _load(source, monkeypatch)
    assert isinstance(namespace["Box"].__dict__["total"], property)
    assert namespace["Box"](2, 3).total == 5
    assert mutants

    namespace, _ = _load(source, monkeypatch, mutant_of="total")
    assert namespace["Box"](2, 3).total == -1


def test_a_context_manager_keeps_working_and_its_mutants_run(monkeypatch):
    source = """
from contextlib import contextmanager

@contextmanager
def scope(value):
    yield value + 1
""".strip()

    namespace, _ = _load(source, monkeypatch)
    with namespace["scope"](1) as inside:
        assert inside == 2

    namespace, _ = _load(source, monkeypatch, mutant_of="scope")
    with namespace["scope"](1) as inside:
        assert inside == 0


def test_a_registering_decorator_runs_once_and_registers_the_trampoline(monkeypatch):
    source = """
REGISTRY = []

def register(fn):
    REGISTRY.append(fn)
    return fn

@register
def double(x):
    return x * 2
""".strip()

    namespace, _ = _load(source, monkeypatch)
    assert [fn(3) for fn in namespace["REGISTRY"]] == [6]

    namespace, _ = _load(source, monkeypatch, mutant_of="double")
    assert [fn(3) for fn in namespace["REGISTRY"]] == [3 / 2]


def test_a_classmethod_under_another_decorator_binds_to_the_subclass(monkeypatch):
    source = """
def marked(fn):
    return fn

class Base:
    @marked
    @classmethod
    def create(cls):
        return cls(1)

class SubClass(Base):
    def __init__(self, value):
        self.value = value
""".strip()

    namespace, _ = _load(source, monkeypatch)
    assert namespace["SubClass"].create().value == 1

    namespace, _ = _load(source, monkeypatch, mutant_of="create")
    assert namespace["SubClass"].create().value is None


def test_an_override_method_is_mutated(monkeypatch):
    source = """
def override(fn):  # typing.override (3.12+) is an identity decorator too
    return fn

class Base:
    def area(self):
        return 0

class Square(Base):
    @override
    def area(self):
        return 2 * 2
""".strip()

    namespace, _ = _load(source, monkeypatch)
    assert namespace["Square"]().area() == 4

    namespace, _ = _load(source, monkeypatch, mutant_of="Squareǁarea")
    assert namespace["Square"]().area() != 4
