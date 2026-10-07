def hello() -> str:
    return "Hello from flat-src!"


def add(a: int, b: int) -> int:
    return a + b


def clamp(value: int, low: int, high: int) -> int:
    if value < low:
        return low
    if value > high:
        return high
    return value


def badly_tested() -> str:
    return "Mutants for this method should survive"
