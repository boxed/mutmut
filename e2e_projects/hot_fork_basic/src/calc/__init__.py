"""Calculator module for mutation testing."""


def divide(a: int, b: int) -> float:
    if b == 0:
        return 0
    return a / b
