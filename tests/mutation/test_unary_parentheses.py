import libcst as cst
import pytest

from mutmut.mutation.file_mutation import mutate_file_contents
from mutmut.mutation.mutators import operator_remove_unary_ops


@pytest.mark.parametrize(
    "source, expected",
    [
        ("not a", "a"),
        ("~a", "a"),
        ("(not a)", "(a)"),
        ("(~a)", "(a)"),
        ("((not (a)))", "(((a)))"),
        ("((~(a)))", "(((a)))"),
        ("(\n    not a\n    < b\n)", "(\n    a\n    < b\n)"),
        ("(\n    ~a\n    ** b\n)", "(\n    a\n    ** b\n)"),
        (
            "( # outer\n    not ( # inner\n        a\n    ) # operand\n)",
            "( # outer\n    ( # inner\n        a\n    ) # operand\n)",
        ),
    ],
)
def test_removed_unary_operator_preserves_parentheses(source, expected):
    node = cst.ensure_type(cst.parse_expression(source), cst.UnaryOperation)
    [mutant] = operator_remove_unary_ops(node)
    code = cst.Module([]).code_for_node(mutant)
    assert code == expected
    compile(code, "<mutant>", "eval")


@pytest.mark.parametrize("operator", ["not ", "~"])
def test_multiline_unary_mutated_file_compiles(operator):
    source = f"def compare(a, b):\n    return (\n        {operator}a\n        < b\n    )\n"
    mutated = mutate_file_contents("example.py", source)
    assert mutated.mutant_names
    compile(mutated.code, "<mutated file>", "exec")


def test_removed_not_keeps_comparison_grouping():
    source = "(not a) == b"
    expression = cst.ensure_type(cst.parse_expression(source), cst.Comparison)
    unary = cst.ensure_type(expression.left, cst.UnaryOperation)
    [operand] = operator_remove_unary_ops(unary)
    code = cst.Module([]).code_for_node(expression.with_changes(left=operand))
    assert code == "(a) == b"
