import sys

import pytest


class MyPlugin:
    def __init__(self):
        self.failed_test_cases = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.outcome == 'failed':
            nodeid = report.nodeid
            self.failed_test_cases.append(nodeid)


def run_tests_return_failed_cases(args):
    my_plugin = MyPlugin()
    pytest.main(
        args,
        plugins=[my_plugin],
    )
    return my_plugin.failed_test_cases


if __name__ == "__main__":
    failed = run_tests_return_failed_cases(sys.argv[1:])
    print(failed)
