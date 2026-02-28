import pytest

from mutmut.workers import timeout


@pytest.fixture(autouse=True)
def clear_timeout_heap() -> None:
    """Clear the timeout heap before each test to avoid pollution."""
    timeout._timeout_heap.clear()
