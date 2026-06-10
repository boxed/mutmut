"""Tests for complex.py module."""

from benchmark import complex


class TestComplex:
    """Test complex call patterns."""

    def test_chain1_entry(self):
        """Strong test - exercises 10-level deep call chain."""
        result = complex.chain1_entry(0)
        assert result == 20  # (0 + 1*10) * 2

    def test_factorial_tail(self):
        """Strong test."""
        assert complex.factorial_tail(5) == 120
        assert complex.factorial_tail(0) == 1
        assert complex.factorial_tail(1) == 1

    def test_sum_tail(self):
        """Strong test."""
        assert complex.sum_tail(10) == 55

    def test_power_tail(self):
        """Strong test."""
        assert complex.power_tail(2, 3) == 8
        assert complex.power_tail(3, 2) == 9

    def test_gcd_tail(self):
        """Strong test."""
        assert complex.gcd_tail(48, 18) == 6

    def test_fibonacci(self):
        """Strong test."""
        assert complex.fibonacci(0) == 0
        assert complex.fibonacci(1) == 1
        assert complex.fibonacci(10) == 55

    def test_flatten(self):
        """Strong test."""
        assert complex.flatten([1, [2, 3], [4, [5]]]) == [1, 2, 3, 4, 5]

    def test_is_even(self):
        """Strong test."""
        assert complex.is_even(4) is True
        assert complex.is_even(3) is False

    def test_is_odd(self):
        """Strong test."""
        assert complex.is_odd(3) is True
        assert complex.is_odd(4) is False

    def test_descend_a(self):
        """Strong test - checks exact value."""
        # 5 -> b(4, 1) -> a(3, 3) -> b(2, 4) -> a(1, 6) -> b(0, 7) -> returns 7
        assert complex.descend_a(5) == 7
        # boundary: n=0 should return acc immediately
        assert complex.descend_a(0) == 0

    def test_apply_twice(self):
        """Strong test."""
        assert complex.apply_twice(lambda x: x + 1, 0) == 2

    def test_apply_n_times(self):
        """Strong test."""
        assert complex.apply_n_times(lambda x: x * 2, 1, 3) == 8

    def test_compose(self):
        """Strong test."""
        f = complex.compose(lambda x: x + 1, lambda x: x * 2)
        assert f(3) == 7  # (3 * 2) + 1

    def test_map_reduce(self):
        """Strong test."""
        result = complex.map_reduce([1, 2, 3], lambda x: x * 2, lambda acc, x: acc + x, 0)
        assert result == 12  # (1*2) + (2*2) + (3*2)

    def test_with_callback(self):
        """Strong test."""
        result = complex.with_callback("data", lambda d: f"success: {d}", lambda e: f"error: {e}")
        assert result == "success: data"

    def test_nested_loops(self):
        """Strong test - checks exact values."""
        # [[1, 2], [3, 4]] -> 1*2 + 2*2 + 3*2 + 4*2 = 20
        assert complex.nested_loops([[1, 2], [3, 4]]) == 20
        # Test with negative values: -1+1 + -2+1 = 0 + -1 = -1
        assert complex.nested_loops([[-1, -2]]) == -1
        # Test boundary: 0 is not > 0, so uses else branch: 0+1 = 1
        assert complex.nested_loops([[0]]) == 1

    def test_nested_conditions(self):
        """Strong test - tests all paths."""
        # x>0, y>0, z>0: x+y+z
        assert complex.nested_conditions(1, 1, 1) == 3
        # x>0, y>0, z<=0: x+y-z
        assert complex.nested_conditions(1, 1, -1) == 3  # 1+1-(-1)=3
        # x>0, y<=0, z>0: x-y+z
        assert complex.nested_conditions(1, -1, 1) == 3  # 1-(-1)+1=3
        # x>0, y<=0, z<=0: x-y-z
        assert complex.nested_conditions(1, -1, -1) == 3  # 1-(-1)-(-1)=3
        # x<=0, y>0: y+z
        assert complex.nested_conditions(-1, 1, 1) == 2
        # x<=0, y<=0: z
        assert complex.nested_conditions(-1, -1, 5) == 5
        # Test boundary: x=0 takes else branch
        assert complex.nested_conditions(0, 1, 1) == 2

    def test_accumulate_with_filter(self):
        """Strong test."""
        result = complex.accumulate_with_filter([1, 2, 3, 4, 5], lambda x: x % 2 == 0, lambda x: x * 10)
        assert result == 60  # (2*10) + (4*10)

    def test_calculate_backoff(self):
        """Strong test - exponential backoff calculation."""
        assert complex.calculate_backoff(0) == 0.0
        assert complex.calculate_backoff(1) == 1.0
        assert complex.calculate_backoff(2) == 2.0
        assert complex.calculate_backoff(3) == 4.0
        # Test max_delay cap
        assert complex.calculate_backoff(10, max_delay=10.0) == 10.0
