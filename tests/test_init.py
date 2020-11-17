
from pytest import raises

from mutmut import (
    partition_node_list,
    name_mutation,
    Context,
    mutate)


def test_partition_node_list_no_nodes():
    with raises(AssertionError):
        partition_node_list([], None)


def test_name_mutation_simple_mutants():
    if name_mutation(None, 'True') != 'False':
        raise AssertionError


def test_context_exclude_line():
    source = "__import__('pkg_resources').declare_namespace(__name__)\n"
    if mutate(Context(source=source)) != (source, 0):
        raise AssertionError

    source = "__all__ = ['hi']\n"
    if mutate(Context(source=source)) != (source, 0):
        raise AssertionError
