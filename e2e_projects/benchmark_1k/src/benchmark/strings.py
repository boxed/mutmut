"""String mutation targets."""


# === Simple strings ===


def messages_batch_1():
    """Simple string literals."""
    a = "hello"
    b = "world"
    return a, b


def labels_batch_1():
    """Label strings."""
    a = "name"
    b = "value"
    return a, b


def states():
    """State strings."""
    a = "pending"
    b = "active"
    return a, b


# === f-strings ===


def format_name(name):
    """f-string with name."""
    return f"Name: {name}"


def format_count(count):
    """f-string with count."""
    return f"Count: {count}"


def format_result(value, unit):
    """f-string with multiple values."""
    return f"Result: {value} {unit}"


# === String method calls ===


def case_methods_1(s):
    """Case conversion."""
    lower = s.lower()
    upper = s.upper()
    return lower, upper


def strip_methods_1(s):
    """Strip methods."""
    left = s.lstrip()
    right = s.rstrip()
    return left, right


def find_methods_1(s, sub):
    """Find methods."""
    pos1 = s.find(sub)
    pos2 = s.rfind(sub)
    return pos1, pos2


def split_methods_1(s, sep):
    """Split methods."""
    parts1 = s.split(sep, 2)
    parts2 = s.rsplit(sep, 2)
    return parts1, parts2


def partition_methods(s, sep):
    """Partition methods."""
    p1 = s.partition(sep)
    p2 = s.rpartition(sep)
    return p1, p2


# === Additional simple strings ===


def messages_batch_2():
    """More string literals."""
    a = "start"
    b = "stop"
    c = "pause"
    return a, b, c


def messages_batch_3():
    """Even more string literals."""
    a = "error"
    b = "warning"
    c = "info"
    d = "debug"
    return a, b, c, d


def symbols():
    """Symbol strings."""
    a = "alpha"
    b = "beta"
    c = "gamma"
    return a, b, c


def keywords():
    """Keyword strings."""
    a = "true"
    b = "false"
    c = "null"
    d = "undefined"
    return a, b, c, d


# === Additional f-strings ===


def format_error(code, message):
    """f-string for error."""
    return f"Error {code}: {message}"


def format_coords(x, y):
    """f-string for coordinates."""
    return f"({x}, {y})"


def format_path(directory, filename):
    """f-string for path."""
    return f"{directory}/{filename}"


def format_greeting(title, name):
    """f-string for greeting."""
    return f"Hello, {title} {name}!"


# === Additional string methods ===


def case_methods_2(s):
    """More case conversion."""
    title = s.title()
    cap = s.capitalize()
    swap = s.swapcase()
    return title, cap, swap


def strip_methods_2(s, chars):
    """Strip with chars."""
    left = s.lstrip(chars)
    right = s.rstrip(chars)
    both = s.strip(chars)
    return left, right, both


def find_methods_2(s, sub, start):
    """Find with start position."""
    pos1 = s.find(sub, start)
    pos2 = s.rfind(sub, start)
    return pos1, pos2


def replace_methods(s, old, new):
    """Replace methods."""
    r1 = s.replace(old, new)
    r2 = s.replace(old, new, 1)
    return r1, r2


def justify_methods(s, width):
    """Justify methods."""
    left = s.ljust(width)
    right = s.rjust(width)
    center = s.center(width)
    return left, right, center


def index_methods(s, sub):
    """Index methods."""
    try:
        i1 = s.index(sub)
        i2 = s.rindex(sub)
        return i1, i2
    except ValueError:
        return -1, -1


def prefix_suffix_methods(s):
    """Prefix/suffix removal."""
    r1 = s.removeprefix("pre_")
    r2 = s.removesuffix("_suf")
    return r1, r2
