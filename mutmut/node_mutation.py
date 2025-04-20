"""This module contains the mutations for individual nodes, e.g. replacing a != b with a == b."""
import re
from typing import Any, Union
from collections.abc import Callable, Iterable, Sequence
import libcst as cst
import libcst.matchers as m

OPERATORS_TYPE = Sequence[
    tuple[
        type[cst.CSTNode],
        Callable[[Any], Iterable[cst.CSTNode]],
    ]
]

def operator_number(
    node: cst.BaseNumber
) -> Iterable[cst.BaseNumber]:
    if isinstance(node, (cst.Integer, cst.Float)):
        yield node.with_changes(value=repr(node.evaluated_value + 1))
    elif isinstance(node, cst.Imaginary):
        yield node.with_changes(value=repr(node.evaluated_value + 1j))
    else:
        print("Unexpected number type", node)


def operator_string(
    node: cst.BaseString
) -> Iterable[cst.BaseString]:
    if isinstance(node, cst.SimpleString):
        value = node.value
        prefix = value[
            : min([x for x in [value.find('"'), value.find("'")] if x != -1])
        ]
        value = value[len(prefix) :]

        if value.startswith('"""') or value.startswith("'''"):
            # We assume here that triple-quoted stuff are docs or other things
            # that mutation is meaningless for
            return

        yield node.with_changes(value=f"{prefix}{value[0]}XX{value[1:-1]}XX{value[-1]}")


def operator_lambda(
    node: cst.Lambda
) -> Iterable[cst.Lambda]:
    if m.matches(node, m.Lambda(body=m.Name("None"))):
        yield node.with_changes(body=cst.Integer("0"))
    else:
        yield node.with_changes(body=cst.Name("None"))


def operator_dict_arguments(
    node: cst.Call
) -> Iterable[cst.Call]:
    """mutate dict(a=b, c=d) to dict(aXX=b, c=d) and dict(a=b, cXX=d)"""
    if not m.matches(node.func, m.Name(value="dict")):
        return

    for i, arg in enumerate(node.args):
        if not arg.keyword:
            return
        keyword = arg.keyword
        mutated_keyword = keyword.with_changes(value=keyword.value + "XX")
        mutated_args = [
            *node.args[:i],
            node.args[i].with_changes(keyword=mutated_keyword),
            *node.args[i+1:],
        ]
        yield node.with_changes(args=mutated_args)


def operator_arg_removal(
    node: cst.Call
) -> Iterable[cst.Call]:
    """try to drop each arg in a function call, e.g. foo(a, b) -> foo(b), foo(a)"""
    for i, arg in enumerate(node.args):
        # replace with None
        if arg.star == '' and not m.matches(arg.value, m.Name("None")):
            mutated_arg = arg.with_changes(value=cst.Name("None"))
            yield node.with_changes(args=[*node.args[:i], mutated_arg, *node.args[i + 1 :]])

    if len(node.args) > 1:
        for i in range(len(node.args)):
            arg = node.args[i]
            yield node.with_changes(args=[*node.args[:i], *node.args[i + 1 :]])


def operator_remove_unary_ops(
    node: cst.UnaryOperation
) -> Iterable[cst.BaseExpression]:
    if isinstance(node.operator, (cst.Not, cst.BitInvert)):
        yield node.expression

_keyword_mapping: dict[type[cst.CSTNode], type[cst.CSTNode]] = {
    cst.Is: cst.IsNot,
    cst.IsNot: cst.Is,
    cst.In: cst.NotIn,
    cst.NotIn: cst.In,
    cst.Break: cst.Return,
    cst.Continue: cst.Break,
}

def operator_keywords(
    node: cst.CSTNode
) -> Iterable[cst.CSTNode]:
    yield from _simple_mutation_mapping(node, _keyword_mapping)


def operator_name(node: cst.Name) -> Iterable[cst.CSTNode]:
    name_mappings = {    
        "True": "False",
        "False": "True",
        "deepcopy": "copy",
        "copy": "deepcopy",

        # common aggregates
        "len": "sum",
        "sum": "len",
        "min": "max",
        "max": "min",

        # boolean checks
        "all": "any",
        "any": "all",

        # ordering
        "sorted":  "reversed",
        "reversed": "sorted",

        # repr vs. str
        "str": "repr",
        "repr": "str",

        # numeric types
        "int": "float",
        "float": "int",

        # sequences vs. tuples
        "list": "tuple",
        "tuple": "list",

        # set types
        "set":  "frozenset",
        "frozenset": "set",

        # byte types
        "bytes": "bytearray",
        "bytearray": "bytes",

        # (optionally) mapping/filtering
        "map": "filter",
        "filter": "map",

        # character/ordinal conversions
        "chr": "ord",
        "ord": "chr",

        # dict ↔ set might be fun… however, beware lol
        # "dict":       "set",
        # "set":        "dict",
    }
    if node.value in name_mappings:
        yield node.with_changes(value=name_mappings[node.value])

_operator_mapping: dict[type[cst.CSTNode], type[cst.CSTNode]] = {
    cst.Plus: cst.Minus,
    cst.Add: cst.Subtract,
    cst.Minus: cst.Plus,
    cst.Subtract: cst.Add,
    cst.Multiply: cst.Divide,
    cst.Divide: cst.Multiply,
    cst.FloorDivide: cst.Divide,
    cst.Modulo: cst.Divide,
    cst.LeftShift: cst.RightShift,
    cst.RightShift: cst.LeftShift,
    cst.BitAnd: cst.BitOr,
    cst.BitOr: cst.BitAnd,
    cst.BitXor: cst.BitAnd,
    cst.Power: cst.Multiply,
    cst.AddAssign: cst.SubtractAssign,
    cst.SubtractAssign: cst.AddAssign,
    cst.MultiplyAssign: cst.DivideAssign,
    cst.DivideAssign: cst.MultiplyAssign,
    cst.FloorDivideAssign: cst.DivideAssign,
    cst.ModuloAssign: cst.DivideAssign,
    cst.LeftShiftAssign: cst.RightShiftAssign,
    cst.RightShiftAssign: cst.LeftShiftAssign,
    cst.BitAndAssign: cst.BitOrAssign,
    cst.BitOrAssign: cst.BitAndAssign,
    cst.BitXorAssign: cst.BitAndAssign,
    cst.PowerAssign: cst.MultiplyAssign,
    cst.LessThan: cst.LessThanEqual,
    cst.LessThanEqual: cst.LessThan,
    cst.GreaterThan: cst.GreaterThanEqual,
    cst.GreaterThanEqual: cst.GreaterThan,
    cst.Equal: cst.NotEqual,
    cst.NotEqual: cst.Equal,
    cst.And: cst.Or,
    cst.Or: cst.And,
}

def operator_swap_op(
    node: cst.CSTNode
) -> Iterable[cst.CSTNode]:
    yield from _simple_mutation_mapping(node, _operator_mapping)


def operator_augmented_assignment(
    node: cst.AugAssign
) -> Iterable[cst.Assign]:
    """mutate all augmented assignments (+=, *=, |=, etc.) to normal = assignments"""
    yield cst.Assign([cst.AssignTarget(node.target)], node.value, node.semicolon)


def operator_assignment(
    node: Union[cst.Assign, cst.AnnAssign]
) -> Iterable[cst.CSTNode]:
    """mutate `a = b` to `a = None` and `a = None` to `a = ""`"""
    if not node.value:
        # do not mutate `a: sometype` to an assignment `a: sometype = ""`
        return
    if m.matches(node.value, m.Name("None")):
        mutated_value = cst.SimpleString('""')
    else:
        mutated_value = cst.Name("None")

    yield node.with_changes(value=mutated_value)

def operator_match(node: cst.Match) -> Iterable[cst.CSTNode]:
    """Drop the case statements in a match."""
    if len(node.cases) > 1:
        for i in range(len(node.cases)):
            yield node.with_changes(cases=[*node.cases[:i], *node.cases[i+1:]])

def _mutate_regex(inner: str) -> list[str]:
    """
    Generate ‘nasty’ variants of a regex body:
     - swap + ↔ *
     - turn `{1,}` ↔ +
     - turn `\d` ↔ `[0-9]` and `\w` ↔ `[A-Za-z0-9_]`
     - reverse the contents of any simple [...] class
    """
    muts: list[str] = []
    # + <-> *
    if "+" in inner:
        muts.append(inner.replace("+", "*"))
    if "*" in inner:
        muts.append(inner.replace("*", "+"))
    # {1,} -> +  and  + -> {1,}
    if re.search(r"\{1,\}", inner):
        muts.append(re.sub(r"\{1,\}", "+", inner))
    if "+" in inner:
        muts.append(re.sub(r"\+", "{1,}", inner))
    # digit class ↔ shorthand
    if "\\d" in inner:
        muts.append(inner.replace("\\d", "[0-9]"))
    if "[0-9]" in inner:
        muts.append(inner.replace("[0-9]", "\\d"))
    # word class ↔ shorthand
    if "\\w" in inner:
        muts.append(inner.replace("\\w", "[A-Za-z0-9_]"))
    if "[A-Za-z0-9_]" in inner:
        muts.append(inner.replace("[A-Za-z0-9_]", "\\w"))
    # reverse simple character classes
    for mobj in re.finditer(r"\[([^\]]+)\]", inner):
        content = mobj.group(1)
        rev = content[::-1]
        orig = f"[{content}]"
        mutated = f"[{rev}]"
        muts.append(inner.replace(orig, mutated))
    # dedupe, preserve order
    return list(dict.fromkeys(muts))


def operator_regex(node: cst.Call) -> Iterable[cst.CSTNode]:
    """
    Look for calls like re.compile(r'…'), re.match, re.search, etc.,
    extract the first SimpleString arg, apply _mutate_regex, and yield
    one mutant per new pattern.
    """
    if not m.matches(
        node,
        m.Call(
            func=m.Attribute(
                value=m.Name("re"),
                attr=m.MatchIfTrue(
                    lambda t: t.value
                    in ("compile", "match", "search", "fullmatch", "findall")
                ),
            ),
            args=[m.Arg(value=m.SimpleString())],
        ),
    ):
        return

    arg = node.args[0]
    lit: cst.SimpleString = arg.value  # type: ignore
    raw = lit.value  # e.g. r'\d+\w*'
    # strip off leading r/R
    prefix = ""
    body = raw
    if raw[:2].lower() == "r'" or raw[:2].lower() == 'r"':
        prefix, body = raw[0], raw[1:]
    quote = body[0]
    inner = body[1:-1]

    for mutated_inner in _mutate_regex(inner):
        new_raw = f"{prefix}{quote}{mutated_inner}{quote}"
        new_lit = lit.with_changes(value=new_raw)
        new_arg = arg.with_changes(value=new_lit)
        yield node.with_changes(args=[new_arg, *node.args[1:]])


# Operators that should be called on specific node types
mutation_operators: OPERATORS_TYPE = [
    (cst.BaseNumber, operator_number),
    (cst.BaseString, operator_string),
    (cst.Name, operator_name),
    (cst.Assign, operator_assignment),
    (cst.AnnAssign, operator_assignment),
    (cst.AugAssign, operator_augmented_assignment),
    (cst.UnaryOperation, operator_remove_unary_ops),
    (cst.Call, operator_dict_arguments),
    (cst.Call, operator_arg_removal),
    (cst.Call, operator_regex),
    (cst.Lambda, operator_lambda),
    (cst.CSTNode, operator_keywords),
    (cst.CSTNode, operator_swap_op),
    (cst.Match, operator_match),
]


def _simple_mutation_mapping(
    node: cst.CSTNode, mapping: dict[type[cst.CSTNode], type[cst.CSTNode]]
) -> Iterable[cst.CSTNode]:
    """Yield mutations from the node class mapping"""
    mutated_node_type = mapping.get(type(node))
    if mutated_node_type:
        yield mutated_node_type()

