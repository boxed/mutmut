from collections import defaultdict

from parso.python.tree import (
    Keyword,
    Name,
    Number,
)

__version__ = '3.2.0'


# We have a global whitelist for constants of the pattern __all__, __version__, etc

dunder_whitelist = [
    'all',
    'version',
    'title',
    'package_name',
    'author',
    'description',
    'email',
    'version',
    'license',
    'copyright',
]

duration_by_test = {}
stats_time = None
config = None

_stats = set()
tests_by_mangled_function_name = defaultdict(set)


class SkipException(Exception):
    pass


UNTESTED = 'untested'
OK_KILLED = 'ok_killed'
OK_SUSPICIOUS = 'ok_suspicious'
BAD_TIMEOUT = 'bad_timeout'
BAD_SURVIVED = 'bad_survived'
SKIPPED = 'skipped'


mutant_statuses = [
    UNTESTED,
    OK_KILLED,
    OK_SUSPICIOUS,
    BAD_TIMEOUT,
    BAD_SURVIVED,
    SKIPPED,
]


def number_mutation(value, **_):
    suffix = ''
    if value.upper().endswith('L'):  # pragma: no cover (python 2 specific)
        suffix = value[-1]
        value = value[:-1]

    if value.upper().endswith('J'):
        suffix = value[-1]
        value = value[:-1]

    if value.startswith('0o'):
        base = 8
        value = value[2:]
    elif value.startswith('0x'):
        base = 16
        value = value[2:]
    elif value.startswith('0b'):
        base = 2
        value = value[2:]
    elif value.startswith('0') and len(value) > 1 and value[1] != '.':  # pragma: no cover (python 2 specific)
        base = 8
        value = value[1:]
    else:
        base = 10

    try:
        parsed = int(value, base=base)
    except ValueError:
        # Since it wasn't an int, it must be a float
        parsed = float(value)

    result = repr(parsed + 1)
    if not result.endswith(suffix):
        result += suffix
    yield dict(value=result)


def string_mutation(value, context, **_):
    if context.is_inside_annassign():
        return

    prefix = value[:min([x for x in [value.find('"'), value.find("'")] if x != -1])]
    value = value[len(prefix):]

    if value.startswith('"""') or value.startswith("'''"):
        # We assume here that triple-quoted stuff are docs or other things
        # that mutation is meaningless for
        return prefix + value
    yield dict(value=prefix + value[0] + 'XX' + value[1:-1] + 'XX' + value[-1])


def partition_node_list(nodes, value):
    for i, n in enumerate(nodes):
        if hasattr(n, 'value') and n.value == value:
            return nodes[:i], n, nodes[i + 1:]

    assert False, "didn't find node to split on"


def lambda_mutation(children, **_):
    pre, op, post = partition_node_list(children, value=':')

    if len(post) == 1 and getattr(post[0], 'value', None) == 'None':
        yield dict(children=pre + [op] + [Number(value=' 0', start_pos=post[0].start_pos)])
    else:
        yield dict(children=pre + [op] + [Keyword(value=' None', start_pos=post[0].start_pos)])


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}


def argument_mutation(children, context, **_):
    if len(context.stack) >= 3 and context.stack[-3].type in ('power', 'atom_expr'):
        stack_pos_of_power_node = -3
    elif len(context.stack) >= 4 and context.stack[-4].type in ('power', 'atom_expr'):
        stack_pos_of_power_node = -4
    else:
        return

    power_node = context.stack[stack_pos_of_power_node]

    # `dict(a=1)` -> `dict(aXX=1)`
    if power_node.children[0].type == 'name' and power_node.children[0].value in context.dict_synonyms:
        c = children[0]
        if c.type == 'name':
            children = children[:]
            children[0] = Name(c.value + 'XX', start_pos=c.start_pos, prefix=c.prefix)
            yield dict(children=children)


def arglist_mutation(children, node, **_):
    for i, child_node in enumerate(children):
        if child_node.type in ('name', 'argument'):
            offset = 1
            if len(children) > i+1:
                if children[i+1].type == 'operator' and children[i+1].value == ',':
                    offset = 2
            yield dict(children=children[:i] + children[i + offset:])


def keyword_mutation(value, context, **_):
    if len(context.stack) > 2 and context.stack[-2].type in ('comp_op', 'sync_comp_for') and value in ('in', 'is'):
        return

    if len(context.stack) > 1 and context.stack[-2].type == 'for_stmt':
        return

    target = {
        'not': '',
        'is': 'is not',  # this will cause "is not not" sometimes, so there's a hack to fix that later
        'in': 'not in',
        # 'break': 'continue',
        # 'continue': 'break',
        'True': 'False',
        'False': 'True',
    }.get(value)

    if target is not None:
        yield dict(value=target)


def operator_mutation(value, node, **_):
    if value in ('*', '**') and node.parent.type in ('param', 'argument'):
        return

    if value == '*' and node.parent.type == 'parameters':
        return

    for op in {
        '+': ['-'],
        '-': ['+'],
        '*': ['/'],
        '/': ['*'],
        '//': ['/'],
        '%': ['/'],
        '<<': ['>>'],
        '>>': ['<<'],
        '&': ['|'],
        '|': ['&'],
        '^': ['&'],
        '**': ['*'],
        '~': [''],

        '+=': ['-=', '='],
        '-=': ['+=', '='],
        '*=': ['/=', '='],
        '/=': ['*=', '='],
        '//=': ['/=', '='],
        '%=': ['/=', '='],
        '<<=': ['>>=', '='],
        '>>=': ['<<=', '='],
        '&=': ['|=', '='],
        '|=': ['&=', '='],
        '^=': ['&=', '='],
        '**=': ['*=', '='],
        '~=': ['='],

        '<': ['<='],
        '<=': ['<'],
        '>': ['>='],
        '>=': ['>'],
        '==': ['!='],
        '!=': ['=='],
        '<>': ['=='],
    }.get(value, []):
        yield dict(value=op)


def and_or_test_mutation(children, node, **_):
    children = children[:]
    children[1] = Keyword(
        value={'and': ' or', 'or': ' and'}[children[1].value],
        start_pos=node.start_pos,
    )
    yield dict(children=children)


def expression_mutation(children, **_):
    def handle_assignment(children):
        mutation_index = -1  # we mutate the last value to handle multiple assignment
        if getattr(children[mutation_index], 'value', '---') != 'None':
            x = ' None'
        else:
            x = ' ""'
        children = children[:]
        children[mutation_index] = Name(value=x, start_pos=children[mutation_index].start_pos)

        return children

    if children[0].type == 'operator' and children[0].value == ':':
        if len(children) > 2 and children[2].value == '=':
            children = children[:]  # we need to copy the list here, to not get in place mutation on the next line!
            children[1:] = handle_assignment(children[1:])
            yield dict(children=children)
    elif children[1].type == 'operator' and children[1].value == '=':
        yield dict(children=handle_assignment(children))


def decorator_mutation(children, **_):
    assert children[-1].type == 'newline'
    yield dict(children=children[-1:])


def name_mutation(node, value, **_):
    simple_mutants = {
        'True': 'False',
        'False': 'True',
        'deepcopy': 'copy',
        'None': '""',
        # TODO: probably need to add a lot of things here... some builtins maybe, what more?
    }
    if value in simple_mutants:
        yield dict(value=simple_mutants[value])

    if node.parent.type == 'trailer' and node.parent.children[0].type == 'operator' and node.parent.children[0].value in ('(', ']'):
        yield dict(value='None')

    # Mutate `b` in `a=b`, but not `a`!
    if node.parent.type == 'argument' and node.parent.children[0] != node and node.parent.children[0].type != 'operator':
        yield dict(value='None')

    # Mutate `b` in `a=b`, but not `a`!
    if node.parent.type == 'arglist':
        yield dict(value='None')


def trailer_mutation(children, **kwargs):
    if children[0].type == 'operator' and children[0].value == '[' and children[-1].type == 'operator' and children[-1].value == ']' and len(children) > 2:
        yield from subscript_mutation(children=children, **kwargs)


def subscript_mutation(children, context, **_):
    if len(children) == 3 and children[1].type == 'keyword' and children[1].value == 'None':
        return
    if context.is_inside_annassign():
        return
    yield dict(children=[
        children[0],
        Name(value='None', start_pos=children[1].start_pos),
        children[-1],
    ])


mutation_by_ast_type = {
    'operator': operator_mutation,
    'keyword': keyword_mutation,
    'number': number_mutation,
    'name': name_mutation,
    'string': string_mutation,
    'argument': argument_mutation,
    'arglist': arglist_mutation,
    'or_test': and_or_test_mutation,
    'and_test': and_or_test_mutation,
    'lambdef': lambda_mutation,
    'expr_stmt': expression_mutation,
    'decorator': decorator_mutation,
    'annassign': expression_mutation,
    'trailer': trailer_mutation,
}

# TODO: detect regexes and mutate them in nasty ways? Maybe mutate all strings as if they are regexes
