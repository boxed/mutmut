import sys

import pytest
from parso import parse

from mutmut.patterns import ASTPattern, array_subscript_pattern, \
    function_call_pattern


@pytest.mark.skipif(sys.version_info < (3, 0),
                    reason="Don't check Python 3 syntax in Python 2")
def test_matches_py3():
    node = parse('a: Optional[int] = 7\n').children[0].children[0].children[
        1].children[1].children[1].children[1]
    assert not array_subscript_pattern.matches(node=node)


def test_matches():
    node = parse('from foo import bar').children[0]
    assert not array_subscript_pattern.matches(node=node)
    assert not function_call_pattern.matches(node=node)
    assert not array_subscript_pattern.matches(node=node)
    assert not function_call_pattern.matches(node=node)

    node = parse('foo[bar]\n').children[0].children[0].children[1].children[1]
    assert array_subscript_pattern.matches(node=node)

    node = parse('foo(bar)\n').children[0].children[0].children[1].children[1]
    assert function_call_pattern.matches(node=node)


def test_ast_pattern_for_loop():
    p = ASTPattern(
        """
for x in y:
#   ^ n  ^ match
    pass
    # ^ x
""",
        x=dict(
            of_type='simple_stmt',
            marker_type='any',
        ),
        n=dict(
            marker_type='name',
        ),
        match=dict(
            marker_type='any',
        )
    )

    n = parse("""for a in [1, 2, 3]:
    if foo:
        continue 
""").children[0].children[3]
    assert p.matches(node=n)

    n = parse("""for a, b in [1, 2, 3]:
    if foo:
        continue 
""").children[0].children[3]
    assert p.matches(node=n)
