from collections.abc import Callable
from functools import cache
from typing import Union
import ctypes
import asyncio


def hello() -> str:
    return "Hello from my-lib!"

def badly_tested() -> str:
    return "Mutants for this method should survive"

def untested() -> str:
    return "Mutants for this method should survive"

def make_greeter(name: Union[str, None]) -> Callable[[], str]:
    def hi():
        if name:
            return "Hi " + name
        else:
            return "Hey there!"

    return hi

def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

async def async_consumer():
    results = []
    async for i in async_generator():
        results.append(i)
    return results

async def async_generator():
    for i in range(10):
        await asyncio.sleep(0.001) # pragma: no mutate
        yield i

def simple_consumer():
    generator = double_generator()
    next(generator) # skip the initial yield
    results = []
    for i in range(10):
        results.append(generator.send(i))
    return results

def double_generator():
    while True:
        x = yield
        yield x * 2

@cache
def cached_fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

    def abs(self) -> 'Point':
        return Point(abs(self.x), abs(self.y))

    def add(self, other: 'Point'):
        self.x += other.x
        self.y += other.y

    def to_origin(self):
        self.x = 0
        self.y = 0

    def ignored(self):
        self.foo = 'bar' # pragma: no mutate

    def __len__(self):
        return 0

    @staticmethod
    def from_coords(coords) -> 'Point':
        return Point(coords[0], coords[1])

    @property
    def coords(self):
        return self.x, self.y


def escape_sequences():
    return "foo" \
           "FOO\\\'\"\a\b\f\n\r\t\v\111\x10\N{ghost}\u1234\U0001F51F"

def create_a_segfault_when_mutated():
    # when we mutate False->True, then this will segfault
    if False:
        ctypes.string_at(0)

def some_func_clone(a, b: str = "111", c: Callable[[str], int] | None = None) -> int | None: pass  # pragma: no mutate
def some_func(a, b: str = "111", c: Callable[[str], int] | None = None) -> int | None:
    if a and c:
        return c(b)
    return None

def func_with_star_clone(a, /, b, *, c, **kwargs): pass  # pragma: no mutate
def func_with_star(a, /, b, *, c, **kwargs):
    return a + b + c + len(kwargs)

def func_with_arbitrary_args_clone(*args, **kwargs): pass  # pragma: no mutate
def func_with_arbitrary_args(*args, **kwargs):
    return len(args) + len(kwargs)