import inspect
from my_lib import *
import pytest
import asyncio

"""These tests are flawed on purpose, some mutants survive and some are killed."""

def test_hello():
    assert hello() == 'Hello from my-lib!'

def test_badly_tested():
    assert badly_tested()

def test_greeter():
    greet = make_greeter("mut")
    assert greet() == "Hi mut"

def test_point():
    p = Point(0, 1)
    p.add(Point(1, 0))

    assert p.x == 1
    assert p.y == 1

    p.to_origin()

    assert p.x == 0

    assert isinstance(p.coords, tuple)

def test_point_from_coords():
    assert Point.from_coords((1, 2)).x == 1


def test_point_skip_static_decorator_pragma():
    assert Point.skip_static_decorator_pragma(3, 4) == 11


def test_point_skip_class_decorator_pragma():
    p = Point.skip_class_decorator_pragma(5)
    assert p.x == 6
    assert p.y == 10


def test_point_skip_instance_method_pragma():
    p = Point(3, 4)
    assert p.skip_instance_method_pragma() == 11


def test_point_skip_multi_decorator():
    p = Point.skip_multi_decorator(5)
    assert p.x == 6
    assert p.y == 10


def test_fibonacci():
    assert fibonacci(1) == 1
    assert cached_fibonacci(1) == 1

def test_escape_sequences():
    assert escape_sequences().lower() == "foofoo\\\'\"\a\b\f\n\r\t\v\111\x10\N{ghost}\u1234\U0001F51F".lower()

def test_simple_consumer():
    # only verifying length, should report surviving mutants for the contents
    assert len(simple_consumer()) == 10

@pytest.mark.asyncio
async def test_async_consumer():
    result = await async_consumer()
    assert result == list(range(10))

def test_handles_segfaults():
    create_a_segfault_when_mutated()

def test_that_signatures_are_preserved():
    assert inspect.signature(some_func) == inspect.signature(some_func_clone)
    assert inspect.signature(func_with_star) == inspect.signature(func_with_star_clone)
    assert inspect.signature(func_with_arbitrary_args) == inspect.signature(func_with_arbitrary_args_clone)

    assert inspect.get_annotations(some_func) == inspect.get_annotations(some_func_clone)
    assert inspect.get_annotations(func_with_star) == inspect.get_annotations(func_with_star_clone)
    assert inspect.get_annotations(func_with_arbitrary_args) == inspect.get_annotations(func_with_arbitrary_args_clone)

def test_signature_functions_are_callable():
    assert some_func(True, c=lambda s: int(s), b="222") == 222
    assert func_with_star(1, b=2, c=3, x='x', y='y', z='z') == 9
    assert func_with_arbitrary_args('a', 'b', foo=123, bar=456) == 4

def test_signature_is_coroutine():
    assert asyncio.iscoroutinefunction(async_consumer)


# Tests for enum mutation
def test_color_enum_values():
    assert Color.RED.value == 1
    assert Color.GREEN.value == 2
    assert Color.BLUE.value == 3


def test_color_is_primary():
    assert Color.RED.is_primary() is True


def test_color_darken():
    assert Color.GREEN.darken() > 0


def test_color_from_name():
    assert Color.from_name("red") == Color.RED
    assert Color.from_name("BLUE") == Color.BLUE


def test_color_default():
    assert Color.default() == Color.RED


def test_skip_this_function():
    assert skip_this_function() == 7


def test_also_skip_this_function():
    assert also_skip_this_function() == "should not mutate"


def test_skip_this_class():
    obj = SkipThisClass()
    assert obj.method_one() == 3
    assert obj.method_two() == "hello world"
    assert SkipThisClass.static_method() == 12


def test_also_skip_this_class():
    obj = AlsoSkipThisClass()
    assert obj.VALUE == 30
    assert obj.compute() == 60


def test_pragma_on_staticmethod_decorator():
    assert Point.pragma_on_staticmethod_decorator(3, 4) == 11


def test_pragma_on_classmethod_decorator():
    p = Point.pragma_on_classmethod_decorator(5)
    assert p.x == 6
    assert p.y == 10


@pytest.mark.asyncio
async def test_color_async_get():
    assert await Color.RED.async_get() == 1
    assert await Color.GREEN.async_get() == 2
    assert await Color.BLUE.async_get() == 3


@pytest.mark.asyncio
async def test_color_async_get_all():
    results = []
    async for color in Color.async_get_all():
        results.append(color)
    assert results == [Color.RED, Color.GREEN, Color.BLUE]
