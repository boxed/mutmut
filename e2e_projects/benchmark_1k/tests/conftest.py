"""
Pytest configuration for benchmark_1k tests.

Simulates real-world test infrastructure costs:
- BENCHMARK_CONFTEST_DELAY: Time for fixture/plugin setup (default: 0.1s)
- BENCHMARK_IMPORT_DELAY: In src/benchmark/__init__.py for library imports
- BENCHMARK_TEST_DELAY: Per-test runtime with +/-10% gaussian jitter (default: 0.1)
"""

import os
import random
import time

import pytest

# Simulate conftest.py costs: fixtures, plugins, pytest hooks
conftest_delay = float(os.environ.get("BENCHMARK_CONFTEST_DELAY", "0.1"))
if conftest_delay > 0:
    time.sleep(conftest_delay)
_test_delay = float(os.environ.get("BENCHMARK_TEST_DELAY", "0.05"))


@pytest.fixture(autouse=True)
def benchmark_test_delay():
    """Add realistic per-test runtime variance."""
    if _test_delay > 0:
        # Apply +/-10% gaussian jitter (std = 10% of mean)
        jittered = random.gauss(_test_delay, _test_delay * 0.1)
        # Clamp to 0.01s
        time.sleep(max(0.01, jittered))
        yield
