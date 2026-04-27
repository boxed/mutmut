"""Complex call patterns."""


# === Deep call chains (10 levels) - Chain 1 ===


def chain1_level_10(x):
    """Chain 1, level 10."""
    return x + 1


def chain1_level_9(x):
    """Chain 1, level 9."""
    return chain1_level_10(x) + 1


def chain1_level_8(x):
    """Chain 1, level 8."""
    return chain1_level_9(x) + 1


def chain1_level_7(x):
    """Chain 1, level 7."""
    return chain1_level_8(x) + 1


def chain1_level_6(x):
    """Chain 1, level 6."""
    return chain1_level_7(x) + 1


def chain1_level_5(x):
    """Chain 1, level 5."""
    return chain1_level_6(x) + 1


def chain1_level_4(x):
    """Chain 1, level 4."""
    return chain1_level_5(x) + 1


def chain1_level_3(x):
    """Chain 1, level 3."""
    return chain1_level_4(x) + 1


def chain1_level_2(x):
    """Chain 1, level 2."""
    return chain1_level_3(x) + 1


def chain1_level_1(x):
    """Chain 1, level 1."""
    return chain1_level_2(x) + 1


def chain1_entry(x):
    """Entry point for chain 1 (10 levels deep)."""
    return chain1_level_1(x) * 2


# === Tail recursion ===


def factorial_tail(n, acc=1):
    """Tail-recursive factorial."""
    if n <= 1:
        return acc
    return factorial_tail(n - 1, acc * n)


def sum_tail(n, acc=0):
    """Tail-recursive sum."""
    if n <= 0:
        return acc
    return sum_tail(n - 1, acc + n)


def power_tail(base, exp, acc=1):
    """Tail-recursive power."""
    if exp <= 0:
        return acc
    return power_tail(base, exp - 1, acc * base)


def gcd_tail(a, b):
    """Tail-recursive GCD."""
    if b == 0:
        return a
    return gcd_tail(b, a % b)


# === Standard recursion ===


def fibonacci(n):
    """Standard recursive fibonacci."""
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)


def flatten(nested):
    """Recursive list flattening."""
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result


# === Mutual recursion ===


def is_even(n):
    """Check even via mutual recursion."""
    if n == 0:
        return True
    if n < 0:
        return is_even(-n)
    return is_odd(n - 1)


def is_odd(n):
    """Check odd via mutual recursion."""
    if n == 0:
        return False
    if n < 0:
        return is_odd(-n)
    return is_even(n - 1)


def descend_a(n, acc=0):
    """Mutual recursion pair A."""
    if n <= 0:
        return acc
    return descend_b(n - 1, acc + 1)


def descend_b(n, acc=0):
    """Mutual recursion pair B."""
    if n <= 0:
        return acc
    return descend_a(n - 1, acc + 2)


# === Higher-order functions ===


def apply_twice(f, x):
    """Apply function twice."""
    return f(f(x))


def apply_n_times(f, x, n):
    """Apply function n times."""
    result = x
    for _ in range(n):
        result = f(result)
    return result


def compose(f, g):
    """Compose two functions."""
    return lambda x: f(g(x))


def map_reduce(items, mapper, reducer, initial):
    """Map-reduce pattern."""
    mapped = [mapper(item) for item in items]
    result = initial
    for item in mapped:
        result = reducer(result, item)
    return result


def with_callback(data, on_success, on_error):
    """Process with callbacks."""
    if data is not None:
        return on_success(data)
    return on_error("no data")


# === Complex nested patterns ===


def nested_loops(matrix):
    """Nested loop processing."""
    total = 0
    for i in range(len(matrix)):
        for j in range(len(matrix[i]) if i < len(matrix) else 0):
            if matrix[i][j] > 0:
                total += matrix[i][j] * 2
            else:
                total += matrix[i][j] + 1
    return total


def nested_conditions(x, y, z):
    """Deeply nested conditions."""
    if x > 0:
        if y > 0:
            if z > 0:
                return x + y + z
            else:
                return x + y - z
        else:
            if z > 0:
                return x - y + z
            else:
                return x - y - z
    else:
        if y > 0:
            return y + z
        else:
            return z


def accumulate_with_filter(items, predicate, transform):
    """Accumulate filtered and transformed items."""
    result = 0
    for item in items:
        if predicate(item):
            transformed = transform(item)
            result += transformed
    return result


def calculate_backoff(attempt, base_delay=1.0, max_delay=60.0):
    """Calculate exponential backoff delay."""
    if attempt <= 0:
        return 0.0
    delay = base_delay * (2 ** (attempt - 1))
    if delay > max_delay:
        return max_delay
    return delay
