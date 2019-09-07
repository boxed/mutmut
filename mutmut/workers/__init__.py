import sys
from io import StringIO
from multiprocessing.connection import Client
from time import time

from mutmut.__main__ import MUTMUT_MASTER_PORT, CMD_FEEDBACK, CMD_QUIT, run_mutation, CMD_MUTATION_DONE, CMD_SET_CONFIG, Config, CMD_RUN_TIMING_BASELINE, CMD_RUN_MUTATION, CMD_TIMING_BASELINE_COMPLETE


def worker_main(tests_pass):
    with Client(('localhost', MUTMUT_MASTER_PORT)) as conn:

        def feedback(line):
            conn.send((CMD_FEEDBACK, line))

        class RealTimeStringIO(StringIO):

            def write(self, *args, **kwargs):
                super(RealTimeStringIO, self).write(*args, **kwargs)
                feedback(' '.join(str(x) for x in args))

        sys.stdout = RealTimeStringIO()
        sys.stderr = RealTimeStringIO()

        config = None

        while True:
            command, params = conn.recv()
            feedback(f'!!{command}, {params}')
            if command == CMD_QUIT:
                return

            if command == CMD_SET_CONFIG:
                config = params
                continue

            if config is None:
                feedback("Incorrect protocol implementation: worker hasn't received a config yet")
                exit(1)

            assert isinstance(config, Config)

            if command == CMD_RUN_MUTATION:
                file_to_mutate, mutation_id = params
                feedback('1111')
                status = run_mutation(config, file_to_mutate, mutation_id, feedback=feedback, tests_pass=tests_pass)
                conn.send((CMD_MUTATION_DONE, (file_to_mutate, mutation_id, status)))

            elif command == CMD_RUN_TIMING_BASELINE:
                start_time = time()
                result = tests_pass(config, feedback, timeout=None)
                time_elapsed = time() - start_time
                conn.send((CMD_TIMING_BASELINE_COMPLETE, (time_elapsed, result)))
