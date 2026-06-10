"""Benchmark package for mutmut warmup strategy testing.

Simulates a real application that imports heavy libraries on startup.
Set BENCHMARK_IMPORT_DELAY environment variable to control the delay.
"""

import os
import time

from benchmark import arguments
from benchmark import booleans
from benchmark import comparisons
from benchmark import complex
from benchmark import numbers
from benchmark import operators
from benchmark import returns
from benchmark import strings

__all__ = [
    "numbers",
    "strings",
    "booleans",
    "operators",
    "comparisons",
    "arguments",
    "returns",
    "complex",
]


# Simulate library imports
import_delay = float(os.environ.get("BENCHMARK_IMPORT_DELAY", "0.05"))
if import_delay > 0:
    time.sleep(import_delay)
