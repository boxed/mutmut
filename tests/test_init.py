from pytest import raises
from mutmut import (
    partition_node_list,
    name_mutation,
    Context,
)


def test_partition_node_list_no_nodes():
    with raises(AssertionError):
        partition_node_list([], None)


def test_name_mutation_simple_mutants():
    assert name_mutation(None, 'True') == 'False'


def test_context_exclude_line():
    context = Context(
        source="__import__('pkg_resources').declare_namespace(__name__)\n"
    )
    assert context.exclude_line() is True

    context = Context(source="__all__ = ['hi']\n")
    assert context.exclude_line() is True
