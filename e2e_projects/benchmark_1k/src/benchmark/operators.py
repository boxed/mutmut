"""Operator mutation targets."""


# === Arithmetic operators ===


def add_sub_1(a, b):
    """Addition and subtraction."""
    add = a + b
    sub = a - b
    return add, sub


def mul_div_1(a, b):
    """Multiplication and division."""
    mul = a * b
    div = a / b if b != 0 else 0
    return mul, div


def integer_ops_1(a, b):
    """Integer operations."""
    floordiv = a // b if b != 0 else 0
    mod = a % b if b != 0 else 0
    return floordiv, mod


def mixed_arithmetic_1(a, b, c):
    """Mixed arithmetic."""
    return a + b * c


# === Bitwise operators ===


def bitwise_shift_1(a):
    """Bit shift."""
    lshift = a << 1
    rshift = a >> 1
    return lshift, rshift


def bitwise_and_or_1(a, b):
    """Bitwise AND/OR."""
    band = a & b
    bor = a | b
    return band, bor


# === Augmented assignment ===


def augmented_add_sub(x):
    """Augmented add/sub."""
    x += 1
    x -= 1
    return x


def augmented_in_loop():
    """Augmented assignment in loop."""
    total = 0
    for i in range(5):
        total += i
    return total


# === Unary operators ===


def unary_not_1(flag):
    """Unary not."""
    return not flag


def unary_invert_1(x):
    """Unary invert."""
    return ~x


def unary_minus(x):
    """Unary minus."""
    return -x


# === Additional arithmetic ===


def add_sub_2(a, b, c):
    """More addition and subtraction."""
    r1 = a + b + c
    r2 = a - b - c
    r3 = a + b - c
    return r1, r2, r3


def mul_div_2(a, b, c):
    """More multiplication and division."""
    r1 = a * b * c
    r2 = a / b / c if b != 0 and c != 0 else 0
    r3 = a * b / c if c != 0 else 0
    return r1, r2, r3


def integer_ops_2(a, b):
    """More integer operations."""
    r1 = a // 2
    r2 = a % 2
    r3 = a**2
    r4 = b // 3
    r5 = b % 3
    return r1, r2, r3, r4, r5


def augmented_batch(value):
    """Batch of augmented assignments."""
    value += 10
    value -= 5
    value *= 2
    value //= 3
    return value


def bitwise_xor_ops(a, b):
    """Bitwise XOR operations."""
    r1 = a ^ b
    r2 = a ^ 0xFF
    r3 = b ^ 0x0F
    return r1, r2, r3
