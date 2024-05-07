from time import time

from mutmut import (
    popen_streaming_output,
    print_status,
)
from mutmut.cache import (
    cached_hash_of_tests,
)
from mutmut.cache import cached_test_time, set_cached_test_time


class TestSuiteTimer:

    def __init__(self, swallow_output: bool, test_command: str, using_testmon: bool, no_progress: bool):

        self.swallow_output = swallow_output
        self.test_command = test_command
        self.using_testmon = using_testmon
        self.no_progress = no_progress

    def run_tests_without_mutations(self):
        """Execute a test suite specified by ``test_command`` and record
        the time it took to execute the test suite as a floating point number

        :return: execution time of the test suite
        """

        output = []

        def feedback(line):
            if not self.swallow_output:
                print(line)
            if not self.no_progress:
                print_status('Running...')
            output.append(line)

        return_code = popen_streaming_output(self.test_command, feedback)

        return return_code, output

    def check_test_run_cleanliness(self, return_code: int) -> bool:
        """
        Check if the test suite ran cleanly without any errors

        :param return_code: return code of the test suite
        :return: True if the test suite ran cleanly without any errors, False otherwise
        """

        return return_code == 0 or (self.using_testmon and return_code == 5)

    def calculate_baseline_time(self, return_code: int, start_time: float, output: list[str]):
        """
        Calculate the baseline time elapsed for the test suite

        :param return_code: return code of the test suite
        :param start_time: start time of the test suite
        :param output: output of the test suite
        :return baseline_time_elapsed: execution time of the test suite
        """

        if self.check_test_run_cleanliness(return_code):
            baseline_time_elapsed = time() - start_time
        else:
            raise RuntimeError(
                "Tests don't run cleanly without mutations. Test command was: {}\n\nOutput:\n\n{}".format(
                    self.test_command,
                    '\n'.join(
                        output)))

        return baseline_time_elapsed

    def time_test_suite(self, current_hash_of_tests) -> float:
        """Execute a test suite specified by ``test_command`` and record
        the time it took to execute the test suite as a floating point number

        :param current_hash_of_tests: hash of the test suite
        :return: execution time of the test suite
        """

        cached_time = cached_test_time()
        if cached_time is not None and current_hash_of_tests == cached_hash_of_tests():
            print('1. Using cached time for baseline tests, to run baseline again delete the cache file')
            return cached_time

        print('1. Running tests without mutations')
        start_time = time()
        return_code, output = self.run_tests_without_mutations()

        baseline_time_elapsed = self.calculate_baseline_time(return_code, start_time, output)
        print('Done')

        set_cached_test_time(baseline_time_elapsed, current_hash_of_tests)

        return baseline_time_elapsed
