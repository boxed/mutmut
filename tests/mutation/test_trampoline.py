"""
Test the trampoline setup.
The functions under test are similar to how file_mutation.py would output the mutated code.
"""

import asyncio
import inspect

import pytest
from typing_extensions import Self

from mutmut.mutation.trampoline import wrap_in_trampoline

mutants_simple_func = {}
mutants_generator_func = {}
mutants_async_func = {}
mutants_async_generator_func = {}
mutants_somenumber__init__ = {}
mutants_somenumber_add = {}
mutants_somenumber_negate = {}
mutants_somenumber_add_zero = {}


@wrap_in_trampoline(mutants_simple_func)
def simple_func(a: int, b: int) -> int:
    return a + b


def simple_func_orig(a: int, b: int) -> int:
    return a + b


def simple_func_1(a: int, b: int) -> int:
    return a - b


@wrap_in_trampoline(mutants_generator_func)
def generator_func(numbers: list[int]):
    for n in numbers:
        yield n * 2


def generator_func_orig(numbers: list[int]):
    for n in numbers:
        yield n * 2


def generator_func_1(numbers: list[int]):
    for n in numbers:
        yield n * 3


@wrap_in_trampoline(mutants_async_func)
async def async_func(a: int, b: int):
    await asyncio.sleep(0)
    return a + b


async def async_func_orig(a: int, b: int):
    await asyncio.sleep(0)
    return a + b


async def async_func_1(a: int, b: int):
    await asyncio.sleep(0)
    return a - b


@wrap_in_trampoline(mutants_async_generator_func)
async def async_generator_func(numbers: list[int]):
    for n in numbers:
        await asyncio.sleep(0)
        yield n * 2


async def async_generator_func_orig(numbers: list[int]):
    for n in numbers:
        await asyncio.sleep(0)
        yield n * 2


async def async_generator_func_1(numbers: list[int]):
    for n in numbers:
        await asyncio.sleep(-1)
        yield n * 3


class SomeNumber:
    @wrap_in_trampoline(mutants_somenumber__init__)
    def __init__(self, number: int):
        self.number = number

    def SomeNumberǁ__init__orig(self, number: int):
        self.number = number

    def SomeNumberǁ__init__1(self, number: int):
        self.number = None  # type: ignore

    @wrap_in_trampoline(mutants_somenumber_add)
    def add(self, number: int) -> Self:
        self.number += number
        return self

    def SomeNumberǁadd_orig(self, number: int) -> Self:
        self.number += number
        return self

    def SomeNumberǁadd_1(self, number: int) -> Self:
        self.number -= number
        return self

    @staticmethod
    @wrap_in_trampoline(mutants_somenumber_negate)
    def negate(number: int) -> int:
        return -number

    @staticmethod
    def SomeNumberǁnegate_orig(number: int) -> int:
        return -number

    @staticmethod
    def SomeNumberǁnegate_1(number: int) -> int:
        return +number

    @classmethod
    @wrap_in_trampoline(mutants_somenumber_add_zero, is_classmethod=True)
    def add_zero(cls, number: int) -> Self:
        return cls(number + 0)

    @classmethod
    def SomeNumberǁadd_zero_orig(cls, number: int) -> Self:
        return cls(number + 0)

    @classmethod
    def SomeNumberǁadd_zero_1(cls, number: int) -> Self:
        return cls(number + 1)


class SomeNumberChild(SomeNumber):
    def __init__(self, number: int):
        super().__init__(number)


mutants_simple_func["_mutmut_orig"] = simple_func_orig
mutants_simple_func["simple_func__mutmut_1"] = simple_func_1
mutants_generator_func["_mutmut_orig"] = generator_func_orig
mutants_generator_func["generator_func__mutmut_1"] = generator_func_1
mutants_async_func["_mutmut_orig"] = async_func_orig
mutants_async_func["async_func__mutmut_1"] = async_func_1
mutants_async_generator_func["_mutmut_orig"] = async_generator_func_orig
mutants_async_generator_func["async_generator_func__mutmut_1"] = async_generator_func_1
mutants_somenumber__init__["_mutmut_orig"] = SomeNumber.SomeNumberǁ__init__orig
mutants_somenumber__init__["SomeNumberǁ__init___mutmut_1"] = SomeNumber.SomeNumberǁ__init__1
mutants_somenumber_add["_mutmut_orig"] = SomeNumber.SomeNumberǁadd_orig
mutants_somenumber_add["SomeNumberǁadd__mutmut_1"] = SomeNumber.SomeNumberǁadd_1
mutants_somenumber_negate["_mutmut_orig"] = SomeNumber.SomeNumberǁnegate_orig
mutants_somenumber_negate["SomeNumberǁnegate__mutmut_1"] = SomeNumber.SomeNumberǁnegate_1
mutants_somenumber_add_zero["_mutmut_orig"] = SomeNumber.SomeNumberǁadd_zero_orig
mutants_somenumber_add_zero["SomeNumberǁadd_zero__mutmut_1"] = SomeNumber.SomeNumberǁadd_zero_1


class TestSimpleFunc:
    def test_trampoline_simple_func_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        assert simple_func(2, 3) == 5, "Should call original function"

    def test_trampoline_simple_func_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.simple_func__mutmut_1")
        assert simple_func(2, 3) == -1, "Should call mutated function"

    def test_trampoline_simple_func_other_module(self, monkeypatch):
        # if we have the same mutant name in a different module, we should not mutate
        monkeypatch.setenv("MUTANT_UNDER_TEST", "other_test_trampoline.simple_func__mutmut_1")
        assert simple_func(2, 3) == 5, "Should call mutated function"


class TestAsyncAndGeneratorFunc:
    def test_generator_func_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        assert list(generator_func([1, 2, 3])) == [2, 4, 6], "Should call original func"

    def test_generator_func_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.generator_func__mutmut_1")
        assert list(generator_func([1, 2, 3])) == [3, 6, 9], "Should call mutated func"

    @pytest.mark.asyncio
    async def test_async_func_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        assert await async_func(2, 3) == 5, "Should call original func"

    @pytest.mark.asyncio
    async def test_async_func_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.async_func__mutmut_1")
        assert await async_func(2, 3) == -1, "Should call mutated func"

    @pytest.mark.asyncio
    async def test_async_generator_func_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        result = []
        async for n in async_generator_func([1, 2, 3]):
            result.append(n)
        assert result == [2, 4, 6], "Should call original func"

    @pytest.mark.asyncio
    async def test_async_generator_func_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.async_generator_func__mutmut_1")
        result = []
        async for n in async_generator_func([1, 2, 3]):
            result.append(n)
        assert result == [3, 6, 9], "Should call mutated func"

    def test_simple_func_is_no_coroutine(self):
        """Normal functions should stay normal functions"""
        assert not inspect.iscoroutinefunction(simple_func)
        assert not inspect.isgeneratorfunction(simple_func)
        assert not inspect.isasyncgenfunction(simple_func)

    def test_async_func_is_coroutine(self):
        """The decorated functions should still be coroutines (e.g. checked by FastAPI)"""
        assert inspect.iscoroutinefunction(async_func)

    def test_generator_funcs_is_generator(self):
        """The decorated functions should still be generators"""
        assert inspect.isgeneratorfunction(generator_func)

    def test_async_generator_is_asyncgen(self):
        """The decorated functions should still be async generators"""
        assert inspect.isasyncgenfunction(async_generator_func)


class TestSimpleClassMethods:
    def test_trampoline_simple_methods_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        n = SomeNumber(123)
        assert n.number == 123, "Should call original __init__"

        n.add(1)
        assert n.number == 124, "Should call original add"

    def test_trampoline_simple_methods_init_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.SomeNumberǁ__init___mutmut_1")
        n = SomeNumber(123)
        assert n.number is None, "Should call mutated __init__"

    def test_trampoline_sipmle_methods_add_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.SomeNumberǁadd__mutmut_1")
        n = SomeNumber(123)
        assert n.number == 123, "Should call original __init__"

        n.add(1)
        assert n.number == 122, "Should call mutated add"


class TestStaticMethods:
    def test_trampoline_staticmethod_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        assert SomeNumber.negate(123) == -123, "Should call original negate on class"
        assert SomeNumber(1).negate(123) == -123, "Should call original negate on instance"

    def test_trampoline_staticmethod_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.SomeNumberǁnegate__mutmut_1")
        assert SomeNumber.negate(123) == 123, "Should call mutated negate on class"
        assert SomeNumber(1).negate(123) == 123, "Should call mutated negate on instance"


class TestClassMethods:
    def test_trampoline_classmethod_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        # on class
        assert type(SomeNumber.add_zero(123)) is SomeNumber, "Should use the class"
        assert SomeNumber.add_zero(123).number == 123, "Should use the original method"
        # on instance
        assert type(SomeNumber(1).add_zero(123)) is SomeNumber, "Should use the class"
        assert SomeNumber(1).add_zero(123).number == 123, "Should use the original method"

    def test_trampoline_classmethod_mutated(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "test_trampoline.SomeNumberǁadd_zero__mutmut_1")
        # on class
        assert type(SomeNumber.add_zero(123)) is SomeNumber, "Should use the class"
        assert SomeNumber.add_zero(123).number == 124, "Should use the mutated method"
        # on instance
        assert type(SomeNumber(1).add_zero(123)) is SomeNumber, "Should use the class"
        assert SomeNumber(1).add_zero(123).number == 124, "Should use the mutated method"

    def test_trampoline_classmethod_baseclass_original(self, monkeypatch):
        monkeypatch.setenv("MUTANT_UNDER_TEST", "")
        assert type(SomeNumberChild.add_zero(123)) is SomeNumberChild, "Should use the subclass"
        # assert type(SomeNumberChild(1).add_zero(123)) is SomeNumberChild, 'Should use the subclass'
        # assert SomeNumberChild.add_zero(123).number == 123, 'Should use the subclass'
