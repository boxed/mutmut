import contextlib
import os
import sys
import shlex
import pytest


class FailedTestCasesPlugin:
    def __init__(self):
        self.failed_test_cases = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.outcome == 'failed':
            nodeid = report.nodeid
            self.failed_test_cases.append(nodeid)


def run_tests_return_failed_cases(args):
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull):
            with contextlib.redirect_stderr(devnull):
                plugin = FailedTestCasesPlugin()
                exit_code = pytest.main(
                    args,
                    plugins=[plugin],
                )

    return exit_code, plugin.failed_test_cases


if __name__ == "__main__":
    exit_code, failed_cases = run_tests_return_failed_cases(sys.argv[1:])
    print("\n".join(failed_cases))
    print()
    exit(exit_code)