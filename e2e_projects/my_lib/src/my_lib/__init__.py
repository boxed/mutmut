from collections.abc import Callable
from enum import Enum
from functools import cache
from typing import AsyncGenerator, Union
import ctypes
import asyncio


def my_decorator(func):  # pragma: no mutate: function
    return func


def hello() -> str:
    return "Hello from my-lib!"

def badly_tested() -> str:
    return "Mutants for this method should survive"

def untested() -> str:
    return "Mutants for this method should survive"

def skip_this_function() -> int:  # pragma: no mutate: function
    return 1 + 2 * 3

def also_skip_this_function() -> str:  # pragma: no mutate function
    return "should" + " not" + " mutate"


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

    @staticmethod
    def skip_static_decorator_pragma(a: int, b: int) -> int:  # pragma: no mutate: function
        return a + b * 2

    @classmethod
    def skip_class_decorator_pragma(cls, value: int) -> "Point":  # pragma: no mutate: function
        return cls(value + 1, value * 2)

    def skip_instance_method_pragma(self) -> int:  # pragma: no mutate: function
        return self.x + self.y * 2

    @staticmethod  # pragma: no mutate: function
    def pragma_on_staticmethod_decorator(a: int, b: int) -> int:
        return a + b * 2

    @classmethod  # pragma: no mutate: function
    def pragma_on_classmethod_decorator(cls, value: int) -> "Point":
        return cls(value + 1, value * 2)

    @my_decorator
    @classmethod
    def skip_multi_decorator(cls, value: int) -> "Point":
        return cls(value + 1, value * 2)


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


class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3

    async def async_get(self) -> int:
        await asyncio.sleep(0.001)
        return self.value

    @staticmethod
    async def async_get_all() -> AsyncGenerator[Color, None]:
        """return type hint here is "wrong" (it's technically AsyncGenerator[int, None])
        but using Color in this context allows us to have a forward reference to the Color class
        that doesn't require quoting the class name (eg. "Color") in the type hint
        that we otherwise would not be able to have in py3.10, and allows us to test that
        trampoline templates are resilient to forward references when using the external trampoline
        pattern.
        """
        for i in (Color.RED, Color.GREEN, Color.BLUE):
            await asyncio.sleep(0.001)
            yield i

    def is_primary(self) -> bool:
        return self in (Color.RED, Color.GREEN, Color.BLUE)

    def darken(self) -> int:
        return self.value - 1

    @staticmethod
    def from_name(name: str) -> "Color":
        return Color[name.upper()]

    @classmethod
    def default(cls) -> "Color":
        return cls.RED


class SkipThisClass:  # pragma: no mutate: class
    def method_one(self) -> int:
        return 1 + 2

    def method_two(self) -> str:
        return "hello" + " world"

    @staticmethod
    def static_method() -> int:
        return 3 * 4


class AlsoSkipThisClass:  # pragma: no mutate class
    VALUE = 10 + 20

    def compute(self) -> int:
        return self.VALUE * 2
