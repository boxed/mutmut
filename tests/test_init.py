
from time import sleep
from pytest import raises
from unittest.mock import MagicMock, patch

from mutmut import (
    partition_node_list,
    name_mutation,
    run_mutation_tests,
    check_mutants,
    OK_KILLED,
    Context, 
    mutate)


def test_partition_node_list_no_nodes():
    with raises(AssertionError):
        partition_node_list([], None)


def test_name_mutation_simple_mutants():
    assert name_mutation(None, 'True') == 'False'


def test_context_exclude_line():
    source = "__import__('pkg_resources').declare_namespace(__name__)\n"
    assert mutate(Context(source=source)) == (source, 0)

    source = "__all__ = ['hi']\n"
    assert mutate(Context(source=source)) == (source, 0)


def check_mutants_stub(**kwargs):
    def run_mutation_stub(*_):
        sleep(0.15)
        return OK_KILLED
    check_mutants_original = check_mutants
    with patch('mutmut.run_mutation', run_mutation_stub):
        check_mutants_original(**kwargs)

class ConfigStub:
    hash_of_tests = None
config_stub = ConfigStub()

def test_run_mutation_tests_thread_synchronization(monkeypatch):
    # arrange
    total_mutants = 3
    cycle_process_after = 1

    def queue_mutants_stub(**kwargs):
        for _ in range(total_mutants):
            kwargs['mutants_queue'].put(('mutant', Context(config=config_stub)))
        kwargs['mutants_queue'].put(('end', None))
    monkeypatch.setattr('mutmut.queue_mutants', queue_mutants_stub)

    def update_mutant_status_stub(**_):
        sleep(0.1)

    monkeypatch.setattr('mutmut.check_mutants', check_mutants_stub)
    monkeypatch.setattr('mutmut.cache.update_mutant_status', update_mutant_status_stub)
    monkeypatch.setattr('mutmut.CYCLE_PROCESS_AFTER', cycle_process_after)

    progress_mock = MagicMock()
    progress_mock.registered_mutants = 0

    def progress_mock_register(*_):
        progress_mock.registered_mutants += 1
        
    progress_mock.register = progress_mock_register

    # act
    run_mutation_tests(config_stub, progress_mock, None)

    # assert
    assert progress_mock.registered_mutants == total_mutants