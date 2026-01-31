from typing import TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from collections.abc import Collection

# verify that mutmut can handle type-check-only annotations
def get_len(data: Collection):
    # (the + 0 is just so we get a surviving and a killed mutant; not relevant for this test case)
    return len(data) + 0

def get_len_clone(data: Collection): pass  # pragma: no mutate


# verify that mutmut can handle annotations that area 
def get_foo_len(data: Foo) -> int:
    return len(data.foo) + 0

def get_foo_len_clone(data: Foo) -> int: pass  # pragma: no mutate

@dataclass
class Foo:
    foo: list[str]
