from enum import Enum
from typing_extensions import Self

def hello() -> str:
    greeting: str = "Hello from type-checking!"
    return greeting

def a_hello_wrapper() -> str:
    # verify that hello() keeps the return type str
    # (if not, this will type error and not be mutated)
    return hello() + "2"

class Person:
    def set_name(self, name: str) -> None:
        self.name = name

    def get_name(self) -> str:
        # type of self.name should be str and compatible with return type
        return self.name

    @classmethod
    def create(cls, name: str) -> Self:
        person = cls()
        person.set_name(name)
        return person

class Employee(Person):
    EMPLOYEE_NUM = 0

    def __init__(self) -> None:
        self.EMPLOYEE_NUM += 1
        self.number = self.EMPLOYEE_NUM

    def set_number(self, number: int) -> Self:
        self.number = number
        return self

    @classmethod
    def new(cls, name: str) -> Self:
        employee = cls()
        employee.set_name(name)
        return employee

class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

    def is_primary(self) -> bool:
        return self in (Color.RED, Color.GREEN, Color.BLUE)

    def darken(self) -> Self:
        return Color.from_index(Color.to_index(self) + 1)

    @staticmethod
    def get_next_color(color: 'Color') -> 'Color':
        return Color.from_index(Color.to_index(color) + 1 % 3)

    @staticmethod
    def to_index(color: 'Color') -> int:
        match color:
            case Color.RED:
                return 0
            case Color.GREEN:
                return 1
            case Color.BLUE:
                return 2

    @staticmethod
    def from_index(index: int) -> 'Color':
        return [Color.RED, Color.GREEN, Color.BLUE][index + 0]

    @classmethod
    def create(cls, name: str) -> Self:
        return cls(name)



def mutate_me() -> str:
    p = Person()
    p.set_name('charlie')
    # Verify that p.get_name keeps the return type str
    name: str = p.get_name()
    return name
