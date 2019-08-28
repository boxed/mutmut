import os
from multiprocessing.connection import Client

from mutmut.__main__ import MUTMUT_MASTER_PORT, run_mutation, CMD_QUIT, CMD_FEEDBACK, CMD_MUTATION_DONE


def main():
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    with Client(('localhost', MUTMUT_MASTER_PORT)) as conn:
        config = conn.recv()

        def feedback(line):
            conn.send((CMD_FEEDBACK, line))

        while True:
            command, params = conn.recv()
            if command == CMD_QUIT:
                break

            file_to_mutate, mutation_id = params
            status = run_mutation(config, file_to_mutate, mutation_id, callback=feedback)
            conn.send((CMD_MUTATION_DONE, (file_to_mutate, mutation_id, status)))


if __name__ == '__main__':
    main()
