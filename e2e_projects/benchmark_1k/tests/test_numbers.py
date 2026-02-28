"""Tests for numbers.py module."""

from benchmark import numbers


class TestNumbers:
    """Test number-heavy functions."""

    def test_constants_batch_1(self):
        """Test constants."""
        result = numbers.constants_batch_1()
        assert result == 3  # 0+1+2

    def test_float_constants_1(self):
        """Test float constants."""
        result = numbers.float_constants_1()
        assert 1.5 < result < 2.5

    def test_negative_constants(self):
        """Test negative constants."""
        result = numbers.negative_constants()
        assert result < 0

    def test_arithmetic_simple(self):
        """Test arithmetic."""
        assert numbers.arithmetic_simple(0) == 1  # 0+1

    def test_loop_range_1(self):
        """Test loop range."""
        result = numbers.loop_range_1()
        assert result == 15  # sum(i+1 for i in range(5))

    def test_threshold_check_1(self):
        """Test threshold check."""
        assert numbers.threshold_check_1(-1) == 0
        assert numbers.threshold_check_1(5) == 1

    def test_array_indices(self):
        """Test array indices."""
        assert numbers.array_indices([1, 2, 3, 4]) == 3  # items[0]+items[1]

    def test_multipliers(self):
        """Test multipliers."""
        result = numbers.multipliers(10)
        assert result == 50  # 10*2 + 10*3 = 50

    def test_offsets(self):
        """Test offsets."""
        result = numbers.offsets(100)
        assert len(result) == 1
        assert result[0] == 101

    def test_dimensions(self):
        """Test dimensions."""
        result = numbers.dimensions()
        assert result == (100, 200)
