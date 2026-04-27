"""Tests for returns.py module."""

from benchmark import returns


class TestReturns:
    """Test return/assignment functions."""

    def test_simple_return_integers(self):
        """Test simple integer return."""
        assert returns.simple_return_integers() == 42

    def test_assign_integers(self):
        """Test integer assignments."""
        result = returns.assign_integers()
        assert result == (1, 2)

    def test_assign_strings(self):
        """Test string assignments."""
        result = returns.assign_strings()
        assert result[0] == "hello"

    def test_assign_lists(self):
        """Test list assignments."""
        result = returns.assign_lists()
        assert result[0] == [1, 2, 3]

    def test_assign_mixed(self):
        """Test mixed assignments."""
        result = returns.assign_mixed()
        assert result == (42, "answer")

    def test_assign_none_batch_1(self):
        """Test None assignments."""
        result = returns.assign_none_batch_1()
        assert all(r is None for r in result)

    def test_typed_int(self):
        """Test typed int."""
        result = returns.typed_int()
        assert result[0] == 42

    def test_typed_str(self):
        """Test typed str."""
        result = returns.typed_str()
        assert result[0] == "test"

    def test_lambda_integers(self):
        """Test lambda integers."""
        f1, f2 = returns.lambda_integers()
        assert f1() == 1
        assert f2() == 2

    def test_lambda_strings(self):
        """Test lambda strings."""
        result = returns.lambda_strings()
        assert result[0]() == "hello"

    def test_lambda_with_args(self):
        """Test lambda with args."""
        result = returns.lambda_with_args()
        assert result[0](5) == 6

    def test_lambda_none_batch_1(self):
        """Test lambda None."""
        f1, f2 = returns.lambda_none_batch_1()
        assert f1() is None

    def test_conditional_assign_1(self):
        """Test conditional assignment."""
        assert returns.conditional_assign_1(True) == "yes"
        assert returns.conditional_assign_1(False) == "no"
