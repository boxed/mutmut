import contextlib
import os
import sys
import shlex
import pytest


class MyPlugin:
    def __init__(self):
        self.failed_test_cases = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call" and report.outcome == 'failed':
            nodeid = report.nodeid
            self.failed_test_cases.append(nodeid)


def run_tests_return_failed_cases(working_dir, args):
    print("pytest ags:",shlex.split(args)[1:])
    with open(os.devnull, 'w') as devnull:
        with contextlib.redirect_stdout(devnull):
            my_plugin = MyPlugin()
            os.chdir(working_dir)
        
            pytest.main(
                # [str(working_dir)],
                shlex.split(args)[1:],
                plugins=[my_plugin],
            )

    return my_plugin.failed_test_cases


if __name__ == "__main__":
    failed = run_tests_return_failed_cases("".join(sys.argv))
    print(failed)
