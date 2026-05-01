"""Return/assignment mutation targets."""


# === Simple return values ===


def simple_return_integers():
    """Simple integer returns."""
    return 42


# === Simple value assignments ===


def assign_integers():
    """Integer assignments."""
    a = 1
    b = 2
    return a, b


def assign_strings():
    """String assignments."""
    a = "hello"
    b = "world"
    return a, b


def assign_lists():
    """List assignments."""
    a = [1, 2, 3]
    return (a,)


def assign_mixed():
    """Mixed type assignments."""
    num = 42
    text = "answer"
    return num, text


# === None assignments ===


def assign_none_batch_1():
    """None assignments."""
    a = None
    b = None
    return a, b


# === Typed assignments ===


def typed_int():
    """Typed integer assignments."""
    x: int = 42
    return (x,)


def typed_str():
    """Typed string assignments."""
    name: str = "test"
    return (name,)


# === Lambdas returning values ===


def lambda_integers():
    """Lambdas returning integers."""
    f1 = lambda: 1  # noqa: E731
    f2 = lambda: 2  # noqa: E731
    return f1, f2


def lambda_strings():
    """Lambdas returning strings."""
    f1 = lambda: "hello"  # noqa: E731
    return (f1,)


def lambda_with_args():
    """Lambdas with arguments."""
    f1 = lambda x: x + 1  # noqa: E731
    return (f1,)


# === Lambdas returning None ===


def lambda_none_batch_1():
    """Lambdas returning None."""
    f1 = lambda: None  # noqa: E731
    f2 = lambda: None  # noqa: E731
    return f1, f2


# === Conditional assignments ===


def conditional_assign_1(flag):
    """Conditional assignment."""
    if flag:
        result = "yes"
    else:
        result = "no"
    return result
