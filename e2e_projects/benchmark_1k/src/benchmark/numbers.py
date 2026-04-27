"""Number mutation targets."""


def constants_batch_1():
    """Numeric constants."""
    a = 0
    b = 1
    c = 2
    return a + b + c


def float_constants_1():
    """Float constants."""
    a = 0.5
    b = 1.5
    return a + b


def negative_constants():
    """Negative numeric constants."""
    a = -1
    b = -2
    return a + b


def arithmetic_simple(x):
    """Simple arithmetic with literals."""
    return x + 1


def loop_range_1():
    """Loop with range literals."""
    total = 0
    for i in range(5):
        total += i + 1
    return total


def threshold_check_1(value):
    """Threshold checking."""
    if value > 0:
        return 1
    return 0


def array_indices(items):
    """Array index access with literals."""
    if len(items) > 2:
        return items[0] + items[1]
    return 0


def multipliers(x):
    """Various multiplier values."""
    a = x * 2
    b = x * 3
    return a + b


def offsets(base):
    """Offset calculations."""
    return [base + 1]


def dimensions():
    """Dimension values."""
    width = 100
    height = 200
    return width, height
