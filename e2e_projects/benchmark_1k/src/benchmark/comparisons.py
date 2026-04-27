"""Comparison mutation targets."""


# === Equality comparisons  ===


def equality_simple(a, b):
    """Simple equality."""
    eq = a == b
    neq = a != b
    return eq, neq


def equality_batch_1(a, b, c):
    """Equality - batch 1."""
    r1 = a == b
    r2 = b == c
    r3 = a != c
    return r1, r2, r3


def equality_with_literals(value):
    """Equality with literals."""
    is_zero = value == 0
    is_one = value == 1
    not_zero = value != 0
    not_one = value != 1
    return is_zero, is_one, not_zero, not_one


def equality_strings(s):
    """String equality."""
    is_empty = s == ""
    is_hello = s == "hello"
    not_empty = s != ""
    return is_empty, is_hello, not_empty


# === Less than comparisons  ===


def less_than_simple(a, b):
    """Simple less than."""
    lt = a < b
    le = a <= b
    return lt, le


def less_than_batch_1(x, y, z):
    """Less than - batch 1."""
    r1 = x < y
    r2 = y < z
    r3 = x <= z
    return r1, r2, r3


def less_than_batch_2(value, threshold):
    """Less than - batch 2."""
    below = value < threshold
    at_or_below = value <= threshold
    return below, at_or_below


def less_than_literals(value):
    """Less than with literals."""
    lt_zero = value < 0
    lt_ten = value < 10
    le_zero = value <= 0
    return lt_zero, lt_ten, le_zero


# === Greater than comparisons  ===


def greater_than_simple(a, b):
    """Simple greater than."""
    gt = a > b
    ge = a >= b
    return gt, ge


def greater_than_batch_1(x, y, z):
    """Greater than - batch 1."""
    r1 = x > y
    r2 = y > z
    r3 = x >= z
    return r1, r2, r3


def greater_than_batch_2(value, threshold):
    """Greater than - batch 2."""
    above = value > threshold
    at_or_above = value >= threshold
    return above, at_or_above


def greater_than_literals(value):
    """Greater than with literals."""
    gt_zero = value > 0
    gt_ten = value > 10
    ge_zero = value >= 0
    return gt_zero, gt_ten, ge_zero


# === Identity comparisons  ===


def identity_none(obj):
    """Identity with None."""
    is_none = obj is None
    is_not_none = obj is not None
    return is_none, is_not_none


def identity_batch_1(a, b):
    """Identity - batch 1."""
    same = a is b
    different = a is not b
    return same, different


def identity_checks(value, default):
    """Multiple identity checks."""
    if value is None:
        return default
    if value is not default:
        return value
    return None


# === Membership comparisons  ===


def membership_simple(item, collection):
    """Simple membership."""
    present = item in collection
    absent = item not in collection
    return present, absent


def membership_batch_1(x, items):
    """Membership - batch 1."""
    r1 = x in items
    r2 = x not in items
    return r1, r2


def membership_string(char, text):
    """String membership."""
    found = char in text
    not_found = char not in text
    return found, not_found


def membership_dict(key, d):
    """Dictionary membership."""
    has_key = key in d
    missing_key = key not in d
    return has_key, missing_key


# === Complex boundary checks  ===


def boundary_check_1(value):
    """Boundary check - batch 1."""
    if value < 0:
        return "negative"
    elif value == 0:
        return "zero"
    elif value <= 10:
        return "small"
    elif value < 100:
        return "medium"
    else:
        return "large"


def boundary_check_2(value, low, high):
    """Boundary check - batch 2."""
    if value < low:
        return "below"
    elif value > high:
        return "above"
    elif value == low:
        return "at_low"
    elif value == high:
        return "at_high"
    else:
        return "within"


def range_check(value, min_val, max_val):
    """Range check."""
    if value < min_val:
        return False
    if value > max_val:
        return False
    if value >= min_val and value <= max_val:
        return True
    return False


def compare_all(a, b):
    """All comparison operators on two values."""
    results = {
        "eq": a == b,
        "ne": a != b,
        "lt": a < b,
        "le": a <= b,
        "gt": a > b,
        "ge": a >= b,
    }
    return results


# === Additional comparisons ===


def chained_comparisons(x, low, mid, high):
    """Chained comparison checks."""
    in_lower = low <= x < mid
    in_upper = mid <= x <= high
    below_all = x < low
    above_all = x > high
    return in_lower, in_upper, below_all, above_all


def multi_condition_check(a, b, c, threshold):
    """Multiple condition checks."""
    all_above = a > threshold and b > threshold and c > threshold
    any_above = a > threshold or b > threshold or c > threshold
    all_equal = a == b == c
    none_below = a >= threshold and b >= threshold and c >= threshold
    return all_above, any_above, all_equal, none_below


def sorted_check(a, b, c):
    """Check if values are sorted."""
    ascending = a < b < c
    descending = a > b > c
    return ascending, descending
