from typing import TYPE_CHECKING, Self
from dataclasses import dataclass

if TYPE_CHECKING:
    from collections.abc import Collection

# verify that mutmut can handle type-check-only annotations
def get_len(data: Collection):
    # (the + 0 is just so we get a surviving and a killed mutant; not relevant for this test case)
    return len(data) + 0

def get_len_clone(data: Collection): pass  # pragma: no mutate


# verify that mutmut can handle annotations that are defined later on
def get_foo_len(data: Foo) -> int:
    return len(data.foo) + 0

def get_foo_len_clone(data: Foo) -> int: pass  # pragma: no mutate

@dataclass
class Foo:
    foo: list[str]

class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

    # verify that we can make forward references to "Point" in classes
    def moved(self, delta_x: int, delta_y: int) -> Point:
        return Point(self.x + delta_x, self.y + delta_y)

    @staticmethod
    def from_tuple(coords: tuple[int, int]) -> Point:
        return Point(coords[0], coords[1])

    @classmethod
    def from_tuple_classmethod(cls, coords: tuple[int, int]) -> Self:
        return cls(coords[0], coords[1])

class SubPoint(Point): pass
