"""Benchmark functions with various argument patterns."""


# === Helper functions ===


def helper_2(a, b):
    """Helper with 2 args."""
    return (a, b)


def helper_3(a, b, c):
    """Helper with 3 args."""
    return (a, b, c)


def combiner(first, second):
    """Combine 2 values."""
    if first is None or second is None:
        return None
    return f"{first}-{second}"


# === 2-arg calls ===


def call_2args_batch_1():
    """2-arg calls."""
    r1 = helper_2(1, 2)
    r2 = helper_2(3, 4)
    return r1, r2


# === 3-arg calls ===


def call_3args_batch_1():
    """3-arg calls."""
    r1 = helper_3(1, 2, 3)
    return (r1,)


# === dict() keyword calls ===


def dict_2keys_batch_1():
    """dict with 2 keys."""
    d1 = {"a": 1, "b": 2}
    return (d1,)


def dict_3keys_batch_1():
    """dict with 3 keys."""
    d1 = {"x": 1, "y": 2, "z": 3}
    return (d1,)


# === String method calls ===


def string_method_calls():
    """String method calls with multiple args."""
    text = "a-b-c-d-e"
    r1 = text.split("-", 2)
    return (r1,)


def format_calls():
    """String format calls."""
    r1 = "{} {}".format("hello", "world")
    return (r1,)
