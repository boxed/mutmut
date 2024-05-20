import multiprocessing
import os
from shutil import (
    move,
    copy,
)
from threading import (
    Timer,
    Thread,
)
from time import time
from typing import Callable, Dict, List

from mutmut.helpers.config import Config
from mutmut.helpers.context import Context
from mutmut.helpers.progress import *
from mutmut.helpers.relativemutationid import RelativeMutationID
from mutmut.mutator.mutator import Mutator

from mutmut.queue_manager import QueueManager
from mutmut.tester.tester_helper import TesterHelper, SkipException

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
try:
    import mutmut_config
except ImportError:
    mutmut_config = None

CYCLE_PROCESS_AFTER = 100


class Tester:
    def __init__(self):
        self.queue_manager = QueueManager()
        self.tester_helper = TesterHelper()

    def run_mutation_tests(self, config: Config, progress: Progress,
                           mutations_by_file: Dict[str, List[RelativeMutationID]]):
        # Need to explicitly use the spawn method for python < 3.8 on macOS
        mp_ctx = multiprocessing.get_context('spawn')

        mutants_queue = mp_ctx.Queue(maxsize=100)
        self.queue_manager.add_to_active_queues(mutants_queue)
        queue_mutants_thread = Thread(
            target=self.queue_manager.queue_mutants,
            name='queue_mutants',
            daemon=True,
            kwargs=dict(
                progress=progress,
                config=config,
                mutants_queue=mutants_queue,
                mutations_by_file=mutations_by_file,
            )
        )
        queue_mutants_thread.start()

        results_queue = mp_ctx.Queue(maxsize=100)
        self.queue_manager.add_to_active_queues(results_queue)

        t = self.create_worker(mp_ctx, mutants_queue, results_queue)

        while True:
            if self.command_results_is_end(mp_ctx, mutants_queue, results_queue, t, config, progress):
                break

    def create_worker(self, mp_ctx, mutants_queue, results_queue):
        t = mp_ctx.Process(
            target=self.check_mutants,
            name='check_mutants',
            daemon=True,
            kwargs=dict(
                mutants_queue=mutants_queue,
                results_queue=results_queue,
                cycle_process_after=CYCLE_PROCESS_AFTER,
            )
        )
        t.start()
        return t

    def command_results_is_end(self, mp_ctx, mutants_queue, results_queue, t, config: Config, progress: Progress):
        from mutmut.cache import update_mutant_status

        command, status, filename, mutation_id = results_queue.get()
        if command == 'end':
            t.join()
            return True

        elif command == 'cycle':
            t = self.create_worker(mp_ctx, mutants_queue, results_queue)
            return False

        elif command == 'progress':
            self.tester_helper.handle_progress(status, config, progress)
            return False

        else:
            assert command == 'status'
            progress.register(status)
            update_mutant_status(file_to_mutate=filename, mutation_id=mutation_id, status=status,
                                 tests_hash=config.hash_of_tests)
            return False

    def check_mutants(self, mutants_queue, results_queue, cycle_process_after):
        def feedback(line):
            results_queue.put(('progress', line, None, None))

        did_cycle = False

        try:
            count = 0
            while True:
                command, context = mutants_queue.get()
                if command == 'end':
                    break

                status = self.run_mutation(context, feedback)

                results_queue.put(('status', status, context.filename, context.mutation_id))
                count += 1
                if count == cycle_process_after:
                    results_queue.put(('cycle', None, None, None))
                    did_cycle = True
                    break
        finally:
            if not did_cycle:
                results_queue.put(('end', None, None, None))

    def run_mutation(self, context: Context, callback) -> str:
        """
        :return: (computed or cached) status of the tested mutant, one of mutant_statuses
        """
        from mutmut.cache import cached_mutation_status
        cached_status = cached_mutation_status(context.filename, context.mutation_id, context.config.hash_of_tests)

        if cached_status != UNTESTED and context.config.total != 1:
            return cached_status

        config = context.config
        # Pre Mutation
        status = self.tester_helper.execute_pre_mutation(context)
        if status is not None:
            return status
        self.tester_helper.execute_config_pre_mutation(config, callback)

        mutator = Mutator(context)

        try:
            mutator.mutate_file(backup=True)
            # Execute Tests
            return self.execute_tests_on_mutation(config, callback)

        except SkipException:
            return SKIPPED

        finally:
            move(mutator.context.filename + '.bak', mutator.context.filename)
            config.test_command = config._default_test_command  # reset test command to its default in the case it was altered in a hook
            # Post Mutation
            self.tester_helper.execute_config_post_mutation(config, callback)

    def execute_tests_on_mutation(self, config: Config, callback):
        start = time()
        try:
            survived = self.tests_pass(config=config, callback=callback)
            if self.tester_helper.should_rerun_tests(config, survived):
                # rerun the whole test suite to be sure the mutant can not be killed by other tests
                config.test_command = config._default_test_command
                survived = self.tests_pass(config=config, callback=callback)
        except TimeoutError:
            return BAD_TIMEOUT

        return self.tester_helper.determine_tests_result(config, start, survived)

    def hammett_tests_pass(self, config: Config, callback) -> bool:
        # noinspection PyUnresolvedReferences
        from hammett import main_cli
        modules_before = set(sys.modules.keys())

        # set up timeout
        import _thread
        from threading import (
            Timer,
            current_thread,
            main_thread,
        )

        timed_out = False

        def timeout():
            _thread.interrupt_main()
            nonlocal timed_out
            timed_out = True

        assert current_thread() is main_thread()
        timer = Timer(config.baseline_time_elapsed * 10, timeout)
        timer.daemon = True
        timer.start()

        # Run tests
        try:
            returncode = self.tester_helper.run_hammett_tests(callback, main_cli, timer, config)
        except KeyboardInterrupt:
            self.tester_helper.handle_keyboard_interrupt(timer, timed_out)

        self.tester_helper.unload_modules(modules_before, config)

        return returncode == 0

    def popen_streaming_output(self, cmd: str, callback: Callable[[str], None], timeout: Optional[float] = None
                               ) -> int:
        """Open a subprocess and stream its output without hard-blocking.

        :param cmd: the command to execute within the subprocess
        :param callback: function that intakes the subprocess' stdout line by line.
            It is called for each line received from the subprocess' stdout stream.
        :param timeout: the timeout time of the subprocess
        :raises TimeoutError: if the subprocess' execution time exceeds
            the timeout time
        :return: the return code of the executed subprocess
        """
        if os.name == 'nt':  # pragma: no cover
            process, stdout = self.tester_helper.start_windows_process(cmd)
        else:
            process, stdout = self.tester_helper.start_other_os_process(cmd)

        # python 2-3 agnostic process timer
        timer = Timer(timeout, self.tester_helper.kill, [process])
        timer.daemon = True
        timer.start()

        while process.returncode is None:
            self.tester_helper.stream_output(stdout, callback)
            if not timer.is_alive():
                raise TimeoutError("subprocess running command '{}' timed out after {} seconds".format(cmd, timeout))
            process.poll()

        # we have returned from the subprocess cancel the timer if it is running
        timer.cancel()

        return process.returncode

    def tests_pass(self, config: Config, callback) -> bool:
        """
        :return: :obj:`True` if the tests pass, otherwise :obj:`False`
        """
        if config.using_testmon:
            copy('.testmondata-initial', '.testmondata')

        use_special_case = True

        # Special case for hammett! We can do in-process test running which is much faster
        if use_special_case and config.test_command.startswith(self.tester_helper.hammett_prefix):
            return self.hammett_tests_pass(config, callback)

        returncode = self.popen_streaming_output(config.test_command, callback,
                                            timeout=config.baseline_time_elapsed * 10)
        return returncode not in (1, 2)
