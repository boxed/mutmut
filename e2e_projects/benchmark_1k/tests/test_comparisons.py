"""Tests for comparisons.py module."""

from benchmark import comparisons


class TestComparisons:
    """Test comparison functions."""

    def test_equality_simple(self):
        """Strong test."""
        eq, neq = comparisons.equality_simple(5, 5)
        assert eq is True
        assert neq is False

    def test_equality_batch_1(self):
        """Strong test - checks all return values."""
        r1, r2, r3 = comparisons.equality_batch_1(1, 1, 2)
        assert r1 is True  # 1 == 1
        assert r2 is False  # 1 == 2
        assert r3 is True  # 1 != 2

    def test_equality_with_literals(self):
        """Strong test - checks all values."""
        result = comparisons.equality_with_literals(0)
        assert result[0] is True  # is_zero
        assert result[1] is False  # is_one
        assert result[2] is False  # not_zero
        assert result[3] is True  # not_one
        # Also test with 1 to catch == 1 / != 1 mutations
        result1 = comparisons.equality_with_literals(1)
        assert result1[1] is True  # is_one

    def test_equality_strings(self):
        """Strong test - checks all values."""
        result = comparisons.equality_strings("")
        assert result[0] is True  # is_empty
        assert result[1] is False  # is_hello
        assert result[2] is False  # not_empty
        # Test with "hello" to catch == "hello" mutation
        result_hello = comparisons.equality_strings("hello")
        assert result_hello[1] is True  # is_hello
        assert result_hello[2] is True  # not_empty

    def test_less_than_simple(self):
        """Strong test - tests boundary to distinguish < from <=."""
        lt, le = comparisons.less_than_simple(3, 5)
        assert lt is True
        assert le is True
        # Test at boundary: 5, 5 - lt should be False, le should be True
        lt_eq, le_eq = comparisons.less_than_simple(5, 5)
        assert lt_eq is False  # 5 < 5 is False
        assert le_eq is True  # 5 <= 5 is True

    def test_less_than_batch_1(self):
        """Strong test - checks all values and boundaries."""
        result = comparisons.less_than_batch_1(1, 2, 3)
        assert result[0] is True  # 1 < 2
        assert result[1] is True  # 2 < 3
        assert result[2] is True  # 1 <= 3
        # Test boundary to distinguish < from <=
        result_eq = comparisons.less_than_batch_1(2, 2, 2)
        assert result_eq[0] is False  # 2 < 2 is False
        assert result_eq[1] is False  # 2 < 2 is False
        assert result_eq[2] is True  # 2 <= 2 is True

    def test_less_than_batch_2(self):
        """Strong test - checks boundary."""
        below, at_or_below = comparisons.less_than_batch_2(5, 10)
        assert below is True
        assert at_or_below is True
        # Test at boundary to distinguish < from <=
        below_eq, at_eq = comparisons.less_than_batch_2(10, 10)
        assert below_eq is False  # 10 < 10 is False
        assert at_eq is True  # 10 <= 10 is True

    def test_less_than_literals(self):
        """Strong test - checks boundaries."""
        result = comparisons.less_than_literals(-1)
        assert result[0] is True  # lt_zero: -1 < 0
        assert result[1] is True  # lt_ten: -1 < 10
        assert result[2] is True  # le_zero: -1 <= 0
        # Test at boundary 0 to distinguish < from <=
        result_zero = comparisons.less_than_literals(0)
        assert result_zero[0] is False  # 0 < 0 is False
        assert result_zero[2] is True  # 0 <= 0 is True

    def test_greater_than_simple(self):
        """Strong test - tests boundary."""
        gt, ge = comparisons.greater_than_simple(5, 3)
        assert gt is True
        assert ge is True
        # Test at boundary to distinguish > from >=
        gt_eq, ge_eq = comparisons.greater_than_simple(5, 5)
        assert gt_eq is False  # 5 > 5 is False
        assert ge_eq is True  # 5 >= 5 is True

    def test_greater_than_batch_1(self):
        """Strong test - checks all values and boundary."""
        result = comparisons.greater_than_batch_1(3, 2, 1)
        assert result[0] is True  # 3 > 2
        assert result[1] is True  # 2 > 1
        assert result[2] is True  # 3 >= 1
        # Test boundary to distinguish > from >=
        result_eq = comparisons.greater_than_batch_1(2, 2, 2)
        assert result_eq[0] is False  # 2 > 2 is False
        assert result_eq[1] is False  # 2 > 2 is False
        assert result_eq[2] is True  # 2 >= 2 is True

    def test_greater_than_batch_2(self):
        """Strong test - checks boundary."""
        above, at_or_above = comparisons.greater_than_batch_2(15, 10)
        assert above is True
        assert at_or_above is True
        # Test at boundary to distinguish > from >=
        above_eq, at_eq = comparisons.greater_than_batch_2(10, 10)
        assert above_eq is False  # 10 > 10 is False
        assert at_eq is True  # 10 >= 10 is True

    def test_greater_than_literals(self):
        """Strong test - checks boundaries."""
        result = comparisons.greater_than_literals(5)
        assert result[0] is True  # gt_zero: 5 > 0
        assert result[1] is False  # gt_ten: 5 > 10 is False
        assert result[2] is True  # ge_zero: 5 >= 0
        # Test at boundary 0 to distinguish > from >=
        result_zero = comparisons.greater_than_literals(0)
        assert result_zero[0] is False  # 0 > 0 is False
        assert result_zero[2] is True  # 0 >= 0 is True

    def test_identity_none(self):
        """Strong test."""
        is_none, is_not_none = comparisons.identity_none(None)
        assert is_none is True
        assert is_not_none is False

    def test_identity_batch_1(self):
        """Strong test - checks both values."""
        obj = object()
        same, different = comparisons.identity_batch_1(obj, obj)
        assert same is True
        assert different is False
        # Test with different objects
        obj2 = object()
        same2, different2 = comparisons.identity_batch_1(obj, obj2)
        assert same2 is False
        assert different2 is True

    def test_identity_checks(self):
        """Coverage test."""
        result = comparisons.identity_checks(5, 10)
        assert result == 5

    def test_membership_simple(self):
        """Strong test."""
        present, absent = comparisons.membership_simple(2, [1, 2, 3])
        assert present is True
        assert absent is False

    def test_membership_batch_1(self):
        """Strong test - checks both values."""
        r1, r2 = comparisons.membership_batch_1(1, [1, 2, 3])
        assert r1 is True  # 1 in [1, 2, 3]
        assert r2 is False  # 1 not in [1, 2, 3] is False
        # Test with missing item
        r1_missing, r2_missing = comparisons.membership_batch_1(99, [1, 2, 3])
        assert r1_missing is False  # 99 in [1, 2, 3] is False
        assert r2_missing is True  # 99 not in [1, 2, 3]

    def test_membership_string(self):
        """Strong test."""
        found, not_found = comparisons.membership_string("a", "abc")
        assert found is True
        assert not_found is False

    def test_membership_dict(self):
        """Strong test."""
        has_key, missing_key = comparisons.membership_dict("a", {"a": 1})
        assert has_key is True
        assert missing_key is False

    def test_boundary_check_1(self):
        """Strong test - tests all boundaries."""
        assert comparisons.boundary_check_1(-1) == "negative"
        assert comparisons.boundary_check_1(0) == "zero"
        assert comparisons.boundary_check_1(5) == "small"
        assert comparisons.boundary_check_1(10) == "small"  # boundary: <= 10
        assert comparisons.boundary_check_1(11) == "medium"  # boundary: > 10, < 100
        assert comparisons.boundary_check_1(99) == "medium"  # boundary: < 100
        assert comparisons.boundary_check_1(100) == "large"  # boundary: >= 100

    def test_boundary_check_2(self):
        """Strong test - tests all cases."""
        assert comparisons.boundary_check_2(-1, 0, 10) == "below"  # < low
        assert comparisons.boundary_check_2(15, 0, 10) == "above"  # > high
        assert comparisons.boundary_check_2(0, 0, 10) == "at_low"  # == low
        assert comparisons.boundary_check_2(10, 0, 10) == "at_high"  # == high
        assert comparisons.boundary_check_2(5, 0, 10) == "within"  # in range

    def test_range_check(self):
        """Strong test - tests boundaries."""
        assert comparisons.range_check(5, 0, 10) is True  # within
        assert comparisons.range_check(0, 0, 10) is True  # at min (>= min_val)
        assert comparisons.range_check(10, 0, 10) is True  # at max (<= max_val)
        assert comparisons.range_check(-1, 0, 10) is False  # below min
        assert comparisons.range_check(11, 0, 10) is False  # above max

    def test_compare_all(self):
        """Strong test - checks all comparison results."""
        result = comparisons.compare_all(5, 3)
        assert result["eq"] is False  # 5 == 3
        assert result["ne"] is True  # 5 != 3
        assert result["lt"] is False  # 5 < 3
        assert result["le"] is False  # 5 <= 3
        assert result["gt"] is True  # 5 > 3
        assert result["ge"] is True  # 5 >= 3
        # Test boundary to distinguish < from <=, > from >=
        result_eq = comparisons.compare_all(5, 5)
        assert result_eq["eq"] is True
        assert result_eq["lt"] is False  # 5 < 5
        assert result_eq["le"] is True  # 5 <= 5
        assert result_eq["gt"] is False  # 5 > 5
        assert result_eq["ge"] is True  # 5 >= 5

    def test_chained_comparisons(self):
        """Strong test - tests boundaries."""
        in_lower, in_upper, below, above = comparisons.chained_comparisons(5, 0, 10, 20)
        assert in_lower is True  # 0 <= 5 < 10
        assert in_upper is False  # 10 <= 5 <= 20 is False
        assert below is False
        assert above is False
        # Test at boundaries
        # x=0: 0 <= 0 < 10 is True
        in_lower_0, _, _, _ = comparisons.chained_comparisons(0, 0, 10, 20)
        assert in_lower_0 is True
        # x=10: 0 <= 10 < 10 is False (< 10 fails), 10 <= 10 <= 20 is True
        in_lower_10, in_upper_10, _, _ = comparisons.chained_comparisons(10, 0, 10, 20)
        assert in_lower_10 is False  # boundary: < 10 fails
        assert in_upper_10 is True  # 10 <= 10 <= 20
        # Test below/above
        _, _, below_neg, _ = comparisons.chained_comparisons(-5, 0, 10, 20)
        assert below_neg is True
        _, _, _, above_30 = comparisons.chained_comparisons(30, 0, 10, 20)
        assert above_30 is True

    def test_multi_condition_check(self):
        """Strong test - tests boundaries and all paths."""
        all_above, any_above, all_equal, none_below = comparisons.multi_condition_check(5, 10, 15, 3)
        assert all_above is True  # all > 3
        assert any_above is True
        assert all_equal is False  # 5 != 10 != 15
        assert none_below is True  # all >= 3
        # Test at threshold boundary (>= vs >)
        all_above_t, any_above_t, _, none_below_t = comparisons.multi_condition_check(3, 3, 3, 3)
        assert all_above_t is False  # 3 > 3 is False
        assert any_above_t is False  # none > 3
        assert none_below_t is True  # all >= 3
        # Test with one above threshold
        all_above_one, any_above_one, _, _ = comparisons.multi_condition_check(2, 2, 5, 3)
        assert all_above_one is False  # not all > 3
        assert any_above_one is True  # 5 > 3
        # Test all equal
        _, _, all_eq, _ = comparisons.multi_condition_check(5, 5, 5, 0)
        assert all_eq is True

    def test_sorted_check(self):
        """Test sorted checks."""
        asc, desc = comparisons.sorted_check(1, 2, 3)
        assert asc is True
        assert desc is False
