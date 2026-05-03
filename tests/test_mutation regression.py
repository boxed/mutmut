from inline_snapshot import snapshot

from mutmut.mutation.file_mutation import mutate_file_contents


def test_module_mutation():
    """Regression test, for a complete module with functions, type annotations and a class"""

    source = """from __future__ import division
from typing import Self
from enum import Enum
import lib

lib.foo()

def foo(a: list[int], b):
    return a[0] > b

def bar():
    yield 1

class Adder:
    def __init__(self, amount):
        self.amount = amount

    def add(self, value):
        return self.amount + value

    @staticmethod
    def negated(adder: "Adder") -> Self:
        return Adder(-adder.amount)

class Color(Enum):
    RED = 'red'
    BLUE = 'blue'

    def darken(self) -> int:
        return self.value - 1

    @staticmethod
    def from_name(name: str) -> "Color":
        return Color[name.upper()]

    @classmethod
    def default(cls) -> "Color":
        return cls.RED


print(Adder(1).add(2))"""

    src, _ = mutate_file_contents("file.py", source)

    assert src == snapshot("""\
from __future__ import division
from typing import Self
from enum import Enum
import lib

lib.foo()


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_x_foo__mutmut: MutantDict = {}  # type: ignore

@_mutmut_mutated(mutants_x_foo__mutmut)
def foo(a: list[int], b):
    return a[0] > b

def x_foo__mutmut_orig(a: list[int], b):
    return a[0] > b

def x_foo__mutmut_1(a: list[int], b):
    return a[1] > b

def x_foo__mutmut_2(a: list[int], b):
    return a[0] >= b

mutants_x_foo__mutmut['_mutmut_orig'] = x_foo__mutmut_orig # type: ignore # mutmut generated
mutants_x_foo__mutmut['x_foo__mutmut_1'] = x_foo__mutmut_1 # type: ignore # mutmut generated
mutants_x_foo__mutmut['x_foo__mutmut_2'] = x_foo__mutmut_2 # type: ignore # mutmut generated
mutants_x_bar__mutmut: MutantDict = {}  # type: ignore

@_mutmut_mutated(mutants_x_bar__mutmut)
def bar():
    yield 1

def x_bar__mutmut_orig():
    yield 1

def x_bar__mutmut_1():
    yield 2

mutants_x_bar__mutmut['_mutmut_orig'] = x_bar__mutmut_orig # type: ignore # mutmut generated
mutants_x_bar__mutmut['x_bar__mutmut_1'] = x_bar__mutmut_1 # type: ignore # mutmut generated
mutants_xǁAdderǁ__init____mutmut: MutantDict = {}  # type: ignore
mutants_xǁAdderǁadd__mutmut: MutantDict = {}  # type: ignore
mutants_xǁAdderǁnegated__mutmut: MutantDict = {}  # type: ignore

class Adder:
    @_mutmut_mutated(mutants_xǁAdderǁ__init____mutmut)
    def __init__(self, amount):
        self.amount = amount
    def xǁAdderǁ__init____mutmut_orig(self, amount):
        self.amount = amount
    def xǁAdderǁ__init____mutmut_1(self, amount):
        self.amount = None

    @_mutmut_mutated(mutants_xǁAdderǁadd__mutmut)
    def add(self, value):
        return self.amount + value

    def xǁAdderǁadd__mutmut_orig(self, value):
        return self.amount + value

    def xǁAdderǁadd__mutmut_1(self, value):
        return self.amount - value

    @staticmethod
    @_mutmut_mutated(mutants_xǁAdderǁnegated__mutmut)
    def negated(adder: "Adder") -> Self:
        return Adder(-adder.amount)

    @staticmethod
    def xǁAdderǁnegated__mutmut_orig(adder: "Adder") -> Self:
        return Adder(-adder.amount)

    @staticmethod
    def xǁAdderǁnegated__mutmut_1(adder: "Adder") -> Self:
        return Adder(None)

    @staticmethod
    def xǁAdderǁnegated__mutmut_2(adder: "Adder") -> Self:
        return Adder(+adder.amount)

mutants_xǁAdderǁ__init____mutmut['_mutmut_orig'] = Adder.xǁAdderǁ__init____mutmut_orig # type: ignore # mutmut generated
mutants_xǁAdderǁ__init____mutmut['xǁAdderǁ__init____mutmut_1'] = Adder.xǁAdderǁ__init____mutmut_1 # type: ignore # mutmut generated

mutants_xǁAdderǁadd__mutmut['_mutmut_orig'] = Adder.xǁAdderǁadd__mutmut_orig # type: ignore # mutmut generated
mutants_xǁAdderǁadd__mutmut['xǁAdderǁadd__mutmut_1'] = Adder.xǁAdderǁadd__mutmut_1 # type: ignore # mutmut generated

mutants_xǁAdderǁnegated__mutmut['_mutmut_orig'] = Adder.xǁAdderǁnegated__mutmut_orig # type: ignore # mutmut generated
mutants_xǁAdderǁnegated__mutmut['xǁAdderǁnegated__mutmut_1'] = Adder.xǁAdderǁnegated__mutmut_1 # type: ignore # mutmut generated
mutants_xǁAdderǁnegated__mutmut['xǁAdderǁnegated__mutmut_2'] = Adder.xǁAdderǁnegated__mutmut_2 # type: ignore # mutmut generated
mutants_xǁColorǁdarken__mutmut: MutantDict = {}  # type: ignore
mutants_xǁColorǁfrom_name__mutmut: MutantDict = {}  # type: ignore

class Color(Enum):
    RED = 'red'
    BLUE = 'blue'

    @_mutmut_mutated(mutants_xǁColorǁdarken__mutmut)
    def darken(self) -> int:
        return self.value - 1

    def xǁColorǁdarken__mutmut_orig(self) -> int:
        return self.value - 1

    def xǁColorǁdarken__mutmut_1(self) -> int:
        return self.value + 1

    def xǁColorǁdarken__mutmut_2(self) -> int:
        return self.value - 2

    @staticmethod
    @_mutmut_mutated(mutants_xǁColorǁfrom_name__mutmut)
    def from_name(name: str) -> "Color":
        return Color[name.upper()]

    @staticmethod
    def xǁColorǁfrom_name__mutmut_orig(name: str) -> "Color":
        return Color[name.upper()]

    @staticmethod
    def xǁColorǁfrom_name__mutmut_1(name: str) -> "Color":
        return Color[name.lower()]

    @classmethod
    def default(cls) -> "Color":
        return cls.RED

mutants_xǁColorǁdarken__mutmut['_mutmut_orig'] = Color.xǁColorǁdarken__mutmut_orig # type: ignore # mutmut generated
mutants_xǁColorǁdarken__mutmut['xǁColorǁdarken__mutmut_1'] = Color.xǁColorǁdarken__mutmut_1 # type: ignore # mutmut generated
mutants_xǁColorǁdarken__mutmut['xǁColorǁdarken__mutmut_2'] = Color.xǁColorǁdarken__mutmut_2 # type: ignore # mutmut generated

mutants_xǁColorǁfrom_name__mutmut['_mutmut_orig'] = Color.xǁColorǁfrom_name__mutmut_orig # type: ignore # mutmut generated
mutants_xǁColorǁfrom_name__mutmut['xǁColorǁfrom_name__mutmut_1'] = Color.xǁColorǁfrom_name__mutmut_1 # type: ignore # mutmut generated


print(Adder(1).add(2))\
""")
