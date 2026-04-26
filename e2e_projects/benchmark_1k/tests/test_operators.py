"""Tests for operators.py module."""

from benchmark import operators


class TestOperators:
    """Test operator functions."""

    def test_add_sub_1(self):
        """Test add/sub."""
        add, sub = operators.add_sub_1(10, 3)
        assert add == 13
        assert sub == 7

    def test_mul_div_1(self):
        """Test mul/div."""
        mul, div = operators.mul_div_1(10, 2)
        assert mul == 20
        assert div == 5

    def test_integer_ops_1(self):
        """Test integer ops."""
        floordiv, mod = operators.integer_ops_1(10, 3)
        assert floordiv == 3
        assert mod == 1

    def test_mixed_arithmetic_1(self):
        """Test mixed arithmetic."""
        assert operators.mixed_arithmetic_1(2, 3, 4) == 14  # 2 + 3*4

    def test_bitwise_shift_1(self):
        """Test bitwise shift."""
        lshift, rshift = operators.bitwise_shift_1(4)
        assert lshift == 8
        assert rshift == 2

    def test_bitwise_and_or_1(self):
        """Test bitwise and/or."""
        band, bor = operators.bitwise_and_or_1(0b1100, 0b1010)
        assert band == 0b1000
        assert bor == 0b1110

    def test_augmented_add_sub(self):
        """Test augmented add/sub."""
        result = operators.augmented_add_sub(10)
        assert result == 10  # 10 + 1 - 1

    def test_augmented_in_loop(self):
        """Test augmented in loop."""
        result = operators.augmented_in_loop()
        assert result == 10  # sum(range(5))

    def test_unary_not_1(self):
        """Test unary not."""
        assert operators.unary_not_1(True) is False
        assert operators.unary_not_1(False) is True

    def test_unary_invert_1(self):
        """Test unary invert."""
        assert operators.unary_invert_1(0) == -1

    def test_unary_minus(self):
        """Test unary minus."""
        assert operators.unary_minus(5) == -5

    def test_add_sub_2(self):
        """Test more add/sub."""
        r1, r2, r3 = operators.add_sub_2(10, 5, 3)
        assert r1 == 18  # 10+5+3
        assert r2 == 2  # 10-5-3
        assert r3 == 12  # 10+5-3

    def test_mul_div_2(self):
        """Test more mul/div."""
        r1, r2, r3 = operators.mul_div_2(2, 3, 4)
        assert r1 == 24  # 2*3*4
        assert r3 == 1.5  # 2*3/4

    def test_integer_ops_2(self):
        """Test more integer ops."""
        r1, r2, r3, r4, r5 = operators.integer_ops_2(10, 11)
        assert r1 == 5  # 10 // 2
        assert r2 == 0  # 10 % 2
        assert r3 == 100  # 10 ** 2

    def test_augmented_batch(self):
        """Test augmented batch."""
        result = operators.augmented_batch(10)
        assert result == 10  # (10+10-5)*2//3 = 30//3 = 10

    def test_bitwise_xor_ops(self):
        """Test bitwise XOR."""
        r1, r2, r3 = operators.bitwise_xor_ops(0b1010, 0b1100)
        assert r1 == 0b0110  # 1010 ^ 1100
