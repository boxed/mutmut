"""Runtime integration tests that use exec() to verify mutated code works at runtime.

These tests sit between unit tests and E2E tests: they generate mutated code
via mutate_file_contents and then exec() it to verify runtime behavior.
"""

import os

from mutmut.mutation.file_mutation import mutate_file_contents


def test_enum_mutation_runtime_execution():
    """Test that mutated enum code can actually be executed and mutants activated."""
    source = """
from enum import Enum

class Color(Enum):
    RED = 1
    GREEN = 2

    def describe(self):
        return self.name.lower()
""".strip()

    mutated_code, mutant_names = mutate_file_contents("test.py", source)
    assert len(mutant_names) > 0, "Should have at least one mutant"

    old_env = os.environ.get("MUTANT_UNDER_TEST")
    try:
        os.environ["MUTANT_UNDER_TEST"] = "none"
        namespace = {"__name__": "test_module"}
        exec(mutated_code, namespace)
        Color = namespace["Color"]

        assert Color.RED.value == 1
        assert Color.GREEN.value == 2

        assert Color.RED.describe() == "red"

        mutant_name = "test_module." + mutant_names[0]
        os.environ["MUTANT_UNDER_TEST"] = mutant_name

        assert Color.RED.describe() == "RED"
    finally:
        if old_env is not None:
            os.environ["MUTANT_UNDER_TEST"] = old_env
        elif "MUTANT_UNDER_TEST" in os.environ:
            del os.environ["MUTANT_UNDER_TEST"]


def test_regular_class_staticmethod_runtime():
    """Test that staticmethod mutation in regular classes works at runtime."""
    source = """
class Calculator:
    @staticmethod
    def add(a, b):
        return a + b
""".strip()

    mutated_code, mutant_names = mutate_file_contents("test.py", source)
    assert len(mutant_names) > 0, "Should have at least one mutant"

    old_env = os.environ.get("MUTANT_UNDER_TEST")
    try:
        os.environ["MUTANT_UNDER_TEST"] = "none"
        namespace = {"__name__": "test_module"}
        exec(mutated_code, namespace)
        Calculator = namespace["Calculator"]

        assert Calculator.add(2, 3) == 5

        mutant_name = "test_module." + mutant_names[0]
        os.environ["MUTANT_UNDER_TEST"] = mutant_name

        assert Calculator.add(5, 3) == 2
    finally:
        if old_env is not None:
            os.environ["MUTANT_UNDER_TEST"] = old_env
        elif "MUTANT_UNDER_TEST" in os.environ:
            del os.environ["MUTANT_UNDER_TEST"]
