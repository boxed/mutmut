from collections.abc import Callable
from functools import cache
from typing import Union


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

    @staticmethod
    def from_coords(coords) -> 'Point':
        return Point(coords[0], coords[1])

    @property
    def coords(self):
        return self.x, self.y