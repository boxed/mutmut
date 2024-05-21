#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

import click

from mutmut import __version__
from mutmut.helpers.progress import MUTANT_STATUSES
from mutmut.helpers.config import config_from_file
from mutmut.cache import (
    create_html_report,
)
from mutmut.cache import print_result_cache, print_result_ids_cache, \
    print_result_cache_junitxml, get_unified_diff
from mutmut.cli.helper.do_apply import do_apply
from mutmut.cli.helper.run import Run


@click.group(context_settings=dict(help_option_names=['-h', '--help']))
def climain():
    """
    Mutation testing system for Python.

    Getting started:

    To run with pytest in test or tests folder: mutmut run

    For more options: mutmut run --help

    To show the results: mutmut results

    To generate HTML report: mutmut html
    """
    pass


@climain.command()
def version():
    """Show the version and exit."""
    print("mutmut version {}".format(__version__))
    sys.exit(0)


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('argument', nargs=1, required=False)
@click.option('--paths-to-mutate', type=click.STRING)
@click.option('--disable-mutation-types', type=click.STRING, help='Skip the given types of mutations.')
@click.option('--enable-mutation-types', type=click.STRING, help='Only perform given types of mutations.')
@click.option('--paths-to-exclude', type=click.STRING)
@click.option('--runner')
@click.option('--use-coverage', is_flag=True, default=False)
@click.option('--use-patch-file', help='Only mutate lines added/changed in the given patch file')
@click.option('--rerun-all', is_flag=True, default=False,
              help='If you modified the test_command in the pre_mutation hook, '
                   'the default test_command (specified by the "runner" option) '
                   'will be executed if the mutant survives with your modified test_command.')
@click.option('--tests-dir')
@click.option('-m', '--test-time-multiplier', default=2.0, type=float)
@click.option('-b', '--test-time-base', default=0.0, type=float)
@click.option('-p', '--test-processes', default=1, type=int)
@click.option('-s', '--swallow-output', help='turn off output capture', is_flag=True)
@click.option('--dict-synonyms')
@click.option('--pre-mutation')
@click.option('--post-mutation')
@click.option('--simple-output', is_flag=True, default=False,
              help="Swap emojis in mutmut output to plain text alternatives.")
@click.option('--no-progress', is_flag=True, default=False, help="Disable real-time progress indicator")
@click.option('--CI', is_flag=True, default=False,
              help="Returns an exit code of 0 for all successful runs and an exit code of 1 for fatal errors.")
@config_from_file(
    dict_synonyms='',
    paths_to_exclude='',
    runner=Run.DEFAULT_RUNNER,
    tests_dir='tests/:test/',
    pre_mutation=None,
    post_mutation=None,
    use_patch_file=None,
)
def run(argument, paths_to_mutate, disable_mutation_types, enable_mutation_types, runner,
        tests_dir, test_time_multiplier, test_time_base, test_processes, swallow_output, use_coverage,
        dict_synonyms, pre_mutation, post_mutation, use_patch_file, paths_to_exclude,
        simple_output, no_progress, ci, rerun_all):
    """
    Runs mutmut. You probably want to start with just trying this. If you supply a mutation ID mutmut will check just this mutant.

    Runs pytest by default (or unittest if pytest is unavailable) on tests in the “tests” or “test” folder.

    It is recommended to configure any non-default options needed in setup.cfg or pyproject.toml, as described in the documentation.

    Exit codes:

     * 0 - all mutants were killed

    Otherwise any or sum of any of the following exit codes:

     * 1 - if a fatal error occurred

     * 2 - if one or more mutants survived

     * 4 - if one or more mutants timed out

     * 8 - if one or more mutants caused tests to take twice as long

    (This is equivalent to a bit-OR combination of the exit codes that may apply.)

    With --CI flag enabled, the exit code will always be
    1 for a fatal error or 0 for any other case.
    """
    if test_time_base is None:  # click sets the default=0.0 to None
        test_time_base = 0.0
    if test_time_multiplier is None:  # click sets the default=0.0 to None
        test_time_multiplier = 0.0

    cli_run = Run(
        argument, paths_to_mutate, disable_mutation_types, enable_mutation_types, runner,
        tests_dir, test_time_multiplier, test_time_base, test_processes, swallow_output, use_coverage,
        dict_synonyms, pre_mutation, post_mutation, use_patch_file, paths_to_exclude,
        simple_output, no_progress, ci, rerun_all
    )

    sys.exit(cli_run.do_run())


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
def results():
    """
    Print the results.
    """
    print_result_cache()
    sys.exit(0)


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('status', nargs=1, required=True)
def result_ids(status):
    """
    Print the IDs of the specified mutant classes (separated by spaces).\n
    result-ids survived (or any other of: killed,timeout,suspicious,skipped,untested)\n
    """
    if not status or status not in MUTANT_STATUSES:
        raise click.BadArgumentUsage(f'The result-ids command needs a status class of mutants '
                                     f'(one of : {set(MUTANT_STATUSES.keys())}) but was {status}')
    print_result_ids_cache(status)
    sys.exit(0)


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('mutation-id', nargs=1, required=True)
@click.option('--backup/--no-backup', default=False)
@click.option('--dict-synonyms')
@config_from_file(
    dict_synonyms='',
)
def apply(mutation_id, backup, dict_synonyms):
    """
    Apply a mutation on disk.
    """
    do_apply(mutation_id, dict_synonyms, backup)
    sys.exit(0)


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('id-or-file', nargs=1, required=False)
@click.option('--dict-synonyms')
@config_from_file(
    dict_synonyms='',
)
def show(id_or_file, dict_synonyms):
    """
    Show a mutation diff.
    """
    if not id_or_file:
        print_result_cache()
        sys.exit(0)

    if id_or_file == 'all':
        print_result_cache(show_diffs=True, dict_synonyms=dict_synonyms)
        sys.exit(0)

    if os.path.isfile(id_or_file):
        print_result_cache(show_diffs=True, only_this_file=id_or_file)
        sys.exit(0)

    print(get_unified_diff(id_or_file, dict_synonyms))
    sys.exit(0)


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--dict-synonyms')
@click.option('--suspicious-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@click.option('--untested-policy', type=click.Choice(['ignore', 'skipped', 'error', 'failure']), default='ignore')
@config_from_file(
    dict_synonyms='',
)
def junitxml(dict_synonyms, suspicious_policy, untested_policy):
    """
    Show a mutation diff with junitxml format.
    """
    print_result_cache_junitxml(dict_synonyms, suspicious_policy, untested_policy)
    sys.exit(0)


@climain.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--dict-synonyms')
@click.option('-d', '--directory', help='Write the output files to DIR.')
@config_from_file(
    dict_synonyms='',
    directory='html',
)
def html(dict_synonyms, directory):
    """
    Generate a HTML report of surviving mutants.
    """
    create_html_report(dict_synonyms, directory)
    sys.exit(0)
