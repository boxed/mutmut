import sys

import pytest
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
    assert name_mutation(None, 'True') == 'False'


@pytest.mark.skipif(sys.version_info < (3, 0), reason="Doesn't work in python2, don't care. Will drop python2 soon enough")
def test_context_exclude_line():
    source = "__import__('pkg_resources').declare_namespace(__name__)\n"
    assert mutate(Context(source=source)) == (source, 0)

    source = "__all__ = ['hi']\n"
    assert mutate(Context(source=source)) == (source, 0)
