import os
import shlex
import subprocess
from io import (
    TextIOBase,
)

from time import time

from mutmut.helpers.config import Config
from mutmut.helpers.context import Context
from mutmut.helpers.progress import *

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
try:
    import mutmut_config
except ImportError:
    mutmut_config = None


class SkipException(Exception):
    pass


class StdOutRedirect(TextIOBase):
    def __init__(self, callback):
        self.callback = callback

    def write(self, s):
        self.callback(s)
        return len(s)


class TesterHelper:
    def __init__(self):
        self.hammett_prefix = 'python -m hammett '

    def handle_progress(self, status, config, progress):
        if not config.swallow_output:
            print(status, end='', flush=True)
        elif not config.no_progress:
            progress.print()

    def execute_pre_mutation(self, context: Context):
        if hasattr(mutmut_config, 'pre_mutation'):
            context.current_line_index = context.mutation_id.line_number
            try:
                mutmut_config.pre_mutation(context=context)
            except SkipException:
                return SKIPPED
            if context.skip:
                return SKIPPED
        return None

    def execute_config_pre_mutation(self, config: Config, callback):
        if config.pre_mutation:
            result = subprocess.check_output(config.pre_mutation, shell=True).decode().strip()
            if result and not config.swallow_output:
                callback(result)

    def should_rerun_tests(self, config: Config, survived):
        # Determines whether tests should be rerun based on the configuration and test results.
        return survived and config.test_command != config._default_test_command and config.rerun_all

    def determine_tests_result(self, config: Config, start, survived):
        time_elapsed = time() - start
        if not survived and time_elapsed > config.test_time_base + (
                config.baseline_time_elapsed * config.test_time_multiplier
        ):
            return OK_SUSPICIOUS

        if survived:
            return BAD_SURVIVED
        else:
            return OK_KILLED

    def execute_config_post_mutation(self, config: Config, callback):
        if config.post_mutation:
            result = subprocess.check_output(config.post_mutation, shell=True).decode().strip()
            if result and not config.swallow_output:
                callback(result)

    def run_hammett_tests(self, callback, main_cli, timer, config: Config):
        redirect = StdOutRedirect(callback)
        sys.stdout = redirect
        sys.stderr = redirect
        returncode = main_cli(shlex.split(config.test_command[len(self.hammett_prefix):]))
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        timer.cancel()
        return returncode

    def handle_keyboard_interrupt(self, timer, timed_out):
        timer.cancel()
        if timed_out:
            raise TimeoutError('In process tests timed out')
        raise

    def unload_modules(self, modules_before, config: Config):
        modules_to_force_unload = {x.partition(os.sep)[0].replace('.py', '') for x in config.paths_to_mutate}

        for module_name in sorted(set(sys.modules.keys()) - set(modules_before), reverse=True):
            if self.should_unload(module_name, modules_to_force_unload):
                del sys.modules[module_name]

    def should_unload(self, module_name, modules_to_force_unload):
        return any(module_name.startswith(x) for x in modules_to_force_unload) or module_name.startswith(
            'tests') or module_name.startswith('django')

    def start_windows_process(self, cmd):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
        )
        stdout = process.stdout
        return process, stdout

    def start_other_os_process(self, cmd):
        master, slave = os.openpty()
        process = subprocess.Popen(
            shlex.split(cmd, posix=True),
            stdout=slave,
            stderr=slave
        )
        stdout = os.fdopen(master)
        os.close(slave)
        return process, stdout

    def kill(self, process_):
        """Kill the specified process on Timer completion"""
        try:
            process_.kill()
        except OSError:
            pass

    def stream_output(self, stdout, callback):
        try:
            if os.name == 'nt':  # pragma: no cover
                self.stream_windows_output(stdout, callback)
            else:
                self.stream_other_os_output(stdout, callback)
        except OSError:
            # This seems to happen on some platforms, including TravisCI.
            # It seems like it's ok to just let this pass here, you just
            # won't get as nice feedback.
            pass

    def stream_windows_output(self, stdout, callback):
        line = stdout.readline()
        # windows gives readline() raw stdout as a b''
        # need to decode it
        line = line.decode("utf-8")
        if line:  # ignore empty strings and None
            callback(line)

    def stream_other_os_output(self, stdout, callback):
        while True:
            line = stdout.readline()
            if not line:
                break
            callback(line)

    def cleanup_backups(self, filenames):
        for filename in filenames:
            if os.path.isfile(f'{filename}.bak'):
                os.remove(f'{filename}.bak')







