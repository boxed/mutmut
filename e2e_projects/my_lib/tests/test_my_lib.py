from my_lib import hello, Point, badly_tested, make_greeter, fibonacci, cached_fibonacci, escape_sequences, simple_consumer, async_consumer
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

