"""Entry point of a ``SpawnRunner`` worker process: tests one mutant, then exits."""

from __future__ import annotations

import json
import sys
import traceback

from mutmut.mutation.trampoline import set_mutant_under_test
from mutmut.runners.harness import PytestRunner
from mutmut.utils.file_utils import setup_source_paths

# A worker that fails outside of the tests exits with this code ("suspicious"). Python's
# own exit code for an uncaught exception is 1, which would be reported as a killed mutant.
WORKER_ERROR_EXIT_CODE = 35


def main() -> int:
    """Returns the exit code of the test run of the mutant read from stdin."""
    try:
        setup_source_paths()
        test_runner = PytestRunner()
        # Workers are started before there is a mutant for them, so this import is paid while waiting.
        import pytest  # noqa: F401

        line = sys.stdin.readline()
        if not line:
            return 0  # The runner shut down without handing this worker a mutant.
        job = json.loads(line)
        set_mutant_under_test(job["mutant_name"])
        return test_runner.run_tests(mutant_name=job["mutant_name"], tests=job["tests"])
    except Exception:
        traceback.print_exc()
        return WORKER_ERROR_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
