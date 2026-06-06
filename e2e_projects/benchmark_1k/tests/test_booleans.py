"""Tests for booleans.py module."""

from benchmark import booleans


class TestBooleans:
    """Test boolean functions."""

    def test_flags_batch_1(self):
        """Strong test - checks all values."""
        enabled, disabled, active, paused = booleans.flags_batch_1()
        assert enabled is True
        assert disabled is False
        assert active is True
        assert paused is False

    def test_flags_batch_2(self):
        """Strong test - checks all values."""
        visible, hidden, selected, focused = booleans.flags_batch_2()
        assert visible is True
        assert hidden is False
        assert selected is True
        assert focused is False

    def test_flags_batch_3(self):
        """Strong test - checks all values."""
        running, stopped, ready, waiting = booleans.flags_batch_3()
        assert running is True
        assert stopped is False
        assert ready is True
        assert waiting is False

    def test_flags_batch_4(self):
        """Strong test - checks all values."""
        valid, invalid, complete, pending = booleans.flags_batch_4()
        assert valid is True
        assert invalid is False
        assert complete is True
        assert pending is False

    def test_conditional_returns_1(self):
        """Strong test."""
        assert booleans.conditional_returns_1(5) is True
        assert booleans.conditional_returns_1(-5) is False

    def test_conditional_returns_2(self):
        """Strong test - checks all paths."""
        assert booleans.conditional_returns_2(5, 5) is True  # x == y
        assert booleans.conditional_returns_2(10, 5) is False  # x > y
        assert booleans.conditional_returns_2(3, 5) is True  # x < y

    def test_default_values(self):
        """Strong test - checks all values."""
        debug, verbose, quiet, strict = booleans.default_values()
        assert debug is False
        assert verbose is False
        assert quiet is True
        assert strict is True

    def test_config_flags(self):
        """Strong test - checks all values."""
        auto_save, auto_load, cache_enabled, logging_enabled = booleans.config_flags()
        assert auto_save is True
        assert auto_load is False
        assert cache_enabled is True
        assert logging_enabled is False

    def test_feature_flags(self):
        """Strong test - checks all values."""
        a, b, c, d = booleans.feature_flags()
        assert a is True
        assert b is False
        assert c is True
        assert d is False

    def test_logical_and_simple(self):
        """Strong test."""
        assert booleans.logical_and_simple(True, True) is True
        assert booleans.logical_and_simple(True, False) is False

    def test_logical_or_simple(self):
        """Strong test."""
        assert booleans.logical_or_simple(False, True) is True
        assert booleans.logical_or_simple(False, False) is False

    def test_logical_and_chain_1(self):
        """Strong test - distinguishes and from or."""
        assert booleans.logical_and_chain_1(True, True, True) is True
        # This would be True if any 'and' became 'or'
        assert booleans.logical_and_chain_1(False, True, True) is False
        assert booleans.logical_and_chain_1(True, False, True) is False

    def test_logical_and_chain_2(self):
        """Weak test."""
        result = booleans.logical_and_chain_2(True, True, True, False)
        assert result is False

    def test_logical_or_chain_1(self):
        """Strong test - distinguishes or from and."""
        assert booleans.logical_or_chain_1(False, False, True) is True
        # This would be False if any 'or' became 'and'
        assert booleans.logical_or_chain_1(True, False, False) is True
        assert booleans.logical_or_chain_1(False, True, False) is True
        assert booleans.logical_or_chain_1(False, False, False) is False

    def test_logical_or_chain_2(self):
        """Strong test - distinguishes or from and."""
        assert booleans.logical_or_chain_2(False, False, False, False) is False
        # These would fail if 'or' became 'and'
        assert booleans.logical_or_chain_2(True, False, False, False) is True
        assert booleans.logical_or_chain_2(False, True, False, False) is True
        assert booleans.logical_or_chain_2(False, False, True, False) is True
        assert booleans.logical_or_chain_2(False, False, False, True) is True

    def test_mixed_logic_1(self):
        """Strong test - (a and b) or (c and d)."""
        # True when a and b are both True
        assert booleans.mixed_logic_1(True, True, False, False) is True
        # True when c and d are both True
        assert booleans.mixed_logic_1(False, False, True, True) is True
        # False when neither pair is both True
        assert booleans.mixed_logic_1(True, False, True, False) is False
        assert booleans.mixed_logic_1(False, True, False, True) is False

    def test_mixed_logic_2(self):
        """Strong test - (a or b) and (c or d)."""
        # True when both pairs have at least one True
        assert booleans.mixed_logic_2(True, False, True, False) is True
        assert booleans.mixed_logic_2(False, True, False, True) is True
        # False when first pair has no True
        assert booleans.mixed_logic_2(False, False, True, True) is False
        # False when second pair has no True
        assert booleans.mixed_logic_2(True, True, False, False) is False

    def test_mixed_logic_3(self):
        """Strong test - a and b or c (precedence: (a and b) or c)."""
        assert booleans.mixed_logic_3(True, True, False) is True  # (T and T) or F = T
        assert booleans.mixed_logic_3(False, True, True) is True  # (F and T) or T = T
        assert booleans.mixed_logic_3(True, False, False) is False  # (T and F) or F = F
        # This catches if 'and' becomes 'or': True or False or False = True
        assert booleans.mixed_logic_3(False, False, False) is False

    def test_mixed_logic_4(self):
        """Strong test - a or b and c (precedence: a or (b and c))."""
        assert booleans.mixed_logic_4(False, True, True) is True  # F or (T and T) = T
        assert booleans.mixed_logic_4(True, False, False) is True  # T or (F and F) = T
        assert booleans.mixed_logic_4(False, True, False) is False  # F or (T and F) = F
        assert booleans.mixed_logic_4(False, False, True) is False  # F or (F and T) = F

    def test_condition_with_and(self):
        """Strong test - detects and/or and comparison mutations."""
        # All positive: first condition True, second condition True, result stays True
        assert booleans.condition_with_and(1, 1, 1) is True
        # x not > 0: first condition fails, second condition (y>0 and z>0) True, result = False and True = False
        assert booleans.condition_with_and(0, 1, 1) is False
        # y not > 0: both conditions fail
        assert booleans.condition_with_and(1, 0, 1) is False
        # y > 0, z not > 0: first True, second fails, result stays True
        assert booleans.condition_with_and(1, 1, 0) is True
        # All zero: both conditions fail
        assert booleans.condition_with_and(0, 0, 0) is False

    def test_condition_with_or(self):
        """Strong test - detects and/or mutations."""
        # x > 0: first or condition True
        assert booleans.condition_with_or(1, 0, 0) is True
        # y > 0: first or condition True
        assert booleans.condition_with_or(0, 1, 0) is True
        # Neither x nor y > 0: first or condition False, result stays True from init
        assert booleans.condition_with_or(0, 0, 0) is True
        # y < 0 or z < 0: second or condition (result or False stays same)
        assert booleans.condition_with_or(-1, -1, 0) is True  # -1 < 0 is True

    def test_complex_condition_1(self):
        """Strong test - (a > 0 and b > 0) or (c > 0 and d > 0)."""
        # First pair True
        assert booleans.complex_condition_1(1, 1, 0, 0) is True
        # Second pair True
        assert booleans.complex_condition_1(0, 0, 1, 1) is True
        # Neither pair True
        assert booleans.complex_condition_1(1, 0, 1, 0) is False
        assert booleans.complex_condition_1(0, 1, 0, 1) is False
        # All zero
        assert booleans.complex_condition_1(0, 0, 0, 0) is False

    def test_guard_clauses(self):
        """Strong test."""
        assert booleans.guard_clauses(5, 0, 10, True) is True
        assert booleans.guard_clauses(None, 0, 10, False) is True
        assert booleans.guard_clauses(15, 0, 10, True) is False

    def test_validation_flags(self):
        """Test validation flags."""
        has_contact, is_complete, is_valid, can_proceed, needs_review = booleans.validation_flags(
            has_name=True, has_email=True, has_phone=False, is_verified=True, is_active=True
        )
        assert has_contact is True
        assert is_complete is True
        assert is_valid is True
        assert can_proceed is True
        assert needs_review is False
