import os
from configparser import ConfigParser

from mutmut.__main__ import Config, popen_streaming_output
from mutmut.workers import worker_main


config_parser = ConfigParser()
config_parser.read('setup.cfg')

test_command = config_parser.get('mutmut', 'test_command', fallback='python -m pytest -x')


def tests_pass(config: Config, feedback, timeout) -> bool:
    """
    :return: :obj:`True` if the tests pass, otherwise :obj:`False`
    """
    returncode = popen_streaming_output(test_command, feedback, timeout=timeout)
    return returncode == 0


def main():
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    worker_main(tests_pass)


if __name__ == '__main__':
    main()
