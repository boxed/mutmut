import itertools
import sys
from typing import Optional

UNTESTED = 'untested'
OK_KILLED = 'ok_killed'
OK_SUSPICIOUS = 'ok_suspicious'
BAD_TIMEOUT = 'bad_timeout'
BAD_SURVIVED = 'bad_survived'
SKIPPED = 'skipped'

MUTANT_STATUSES = {
    "killed": OK_KILLED,
    "timeout": BAD_TIMEOUT,
    "suspicious": OK_SUSPICIOUS,
    "survived": BAD_SURVIVED,
    "skipped": SKIPPED,
    "untested": UNTESTED,
}


class Progress:
    def __init__(self, total, output_legend, no_progress=False):
        self.total = total
        self.output_legend = output_legend
        self.progress = 0
        self.skipped = 0
        self.killed_mutants = 0
        self.surviving_mutants = 0
        self.surviving_mutants_timeout = 0
        self.suspicious_mutants = 0
        self.no_progress = no_progress

    def print(self):
        if self.no_progress:
            return
        print_status('{}/{}  {} {}  {} {}  {} {}  {} {}  {} {}'.format(
            self.progress,
            self.total,
            self.output_legend["killed"],
            self.killed_mutants,
            self.output_legend["timeout"],
            self.surviving_mutants_timeout,
            self.output_legend["suspicious"],
            self.suspicious_mutants,
            self.output_legend["survived"],
            self.surviving_mutants,
            self.output_legend["skipped"],
            self.skipped)
        )

    def register(self, status):
        if status == BAD_SURVIVED:
            self.surviving_mutants += 1
        elif status == BAD_TIMEOUT:
            self.surviving_mutants_timeout += 1
        elif status == OK_KILLED:
            self.killed_mutants += 1
        elif status == OK_SUSPICIOUS:
            self.suspicious_mutants += 1
        elif status == SKIPPED:
            self.skipped += 1
        else:
            raise ValueError('Unknown status returned from run_mutation: {}'.format(status))
        self.progress += 1
        self.print()

    def compute_exit_code(self, exception: Optional[Exception] = None, ci: bool = False) -> int:
        """Compute an exit code for mutmut mutation testing

        The following exit codes are available for mutmut (as documented for the CLI run command):
         * 0 if all mutants were killed (OK_KILLED)
         * 1 if a fatal error occurred
         * 2 if one or more mutants survived (BAD_SURVIVED)
         * 4 if one or more mutants timed out (BAD_TIMEOUT)
         * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)

         Exit codes 1 to 8 will be bit-ORed so that it is possible to know what
         different mutant statuses occurred during mutation testing.

         When running with ci=True (--CI flag enabled), the exit code will always be
         1 for a fatal error or 0 for any other case.

        :param exception:
        :param progress:
        :param ci:

        :return: integer noting the exit code of the mutation tests.
        """
        code = 0
        if exception is not None:
            code = code | 1
        if ci:
            return code
        if self.surviving_mutants > 0:
            code = code | 2
        if self.surviving_mutants_timeout > 0:
            code = code | 4
        if self.suspicious_mutants > 0:
            code = code | 8
        return code


def status_printer():
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]

    def p(s):
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        sys.stdout.write(output)
        sys.stdout.flush()
        last_len[0] = len_s

    return p


spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')
print_status = status_printer()
