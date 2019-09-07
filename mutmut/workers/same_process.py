import os
import sys
from configparser import ConfigParser

from mutmut.__main__ import Config
from mutmut.workers import worker_main

# TODO: implement timeouts!

config_parser = ConfigParser()
config_parser.read('setup.cfg')

runner_setup = config_parser.get('mutmut', 'runner_setup', fallback='import pytest')
startup_imports = config_parser.get('mutmut', 'startup_imports', fallback='pytest.main(["--invalid_parameter_on_purpose_to_make_pytest_import_its_stuff_but_then_error_out"])')
test_command = config_parser.get('mutmut', 'test_command', fallback='pytest.main(["-x"])')
dependency_imports = config_parser.get('mutmut', 'dependency_imports', fallback='')


def tests_pass(config: Config, feedback, timeout) -> bool:
    """
    :return: :obj:`True` if the tests pass, otherwise :obj:`False`
    """
    del config
    del feedback  # own process stdio/stderr forwarding is handled in __init__.py
    restore_imports_checkpoint()

    try:
        exec(runner_setup)
        returncode = eval(test_command)
    except BaseException:
        # We can crash out from pytest at import time by mutants!
        return False
    return returncode == 0


imports_checkpoint = set()


def restore_imports_checkpoint():
    assert imports_checkpoint
    for k in sys.modules.copy().keys():
        if k not in imports_checkpoint:
            del sys.modules[k]


def main():
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'  # stop python from creating .pyc files

    if dependency_imports:
        exec(dependency_imports)

    try:
        exec(runner_setup)
    except SystemExit:
        # pytest.main calls sys.exit instead of exiting cleanly :(
        pass
    # try:
    #     exec(startup_imports)
    # except SystemExit:
    #     # pytest.main calls sys.exit instead of exiting cleanly :(
    #     pass

    imports_checkpoint.update(set(sys.modules.keys()))
    assert imports_checkpoint
    worker_main(tests_pass)


if __name__ == '__main__':
    main()
