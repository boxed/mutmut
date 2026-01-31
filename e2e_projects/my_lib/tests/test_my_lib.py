import inspect
from my_lib import *
import pytest

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
    assert func_with_star(1, b=2, x='x', y='y', z='z') == 6
    assert func_with_arbitrary_args('a', 'b', foo=123, bar=456) == 4
