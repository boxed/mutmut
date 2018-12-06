#!/usr/bin/python
# -*- coding: utf-8 -*-

"""mutation testing definitions and helpers"""

from logging import getLogger

from parso import parse
from parso.python.tree import Name
from tri.declarative import evaluate

__log__ = getLogger(__name__)

ALL = ('all', -1)


# variable names we should skip modifying as we are sure that proper
# python practice avoids this being sificant to mutate
SKIP_NAMES = [
    "__author__",
    "__copyright__",
    "__license__",
    "__version__",
    "__summary__"
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
    elif value.startswith('0') and len(value) > 1 and value[
        1] != '.':  # pragma: no cover (python 2 specific)
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
    return result


def string_mutation(value, **_):
    prefix = value[
             :min([x for x in [value.find('"'), value.find("'")] if x != -1])]
    value = value[len(prefix):]

    if value.startswith('"""') or value.startswith("'''"):
        # We assume here that triple-quoted stuff are docs or other things
        # that mutation is meaningless for
        return value
    return prefix + value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]


def lambda_mutation(children, **_):
    from parso.python.tree import Name
    if len(children) != 4 or getattr(children[-1], 'value', '---') != 'None':
        return children[:3] + [
            Name(value=' None', start_pos=children[0].start_pos)]
    else:
        return children[:3] + [
            Name(value=' 0', start_pos=children[0].start_pos)]


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}


def argument_mutation(children, context, **_):
    """
    :type context: MutationContext
    """
    if len(context.stack) >= 3 and \
            context.stack[-3].type in ('power', 'atom_expr'):
        stack_pos_of_power_node = -3
    elif len(context.stack) >= 4 and \
            context.stack[-4].type in ('power', 'atom_expr'):
        stack_pos_of_power_node = -4
    else:
        return children

    power_node = context.stack[stack_pos_of_power_node]

    if power_node.children[0].type == 'name' and \
            power_node.children[0].value in context.dict_synonyms:
        children = children[:]
        from parso.python.tree import Name
        c = children[0]
        if c.type == 'name':
            children[0] = Name(c.value + 'XX', start_pos=c.start_pos,
                               prefix=c.prefix)

    return children


def keyword_mutation(value, context, **_):
    if len(context.stack) > 2 and \
            context.stack[-2].type == 'comp_op' and \
            value in ('in', 'is'):
        return value

    if len(context.stack) > 1 and context.stack[-2].type == 'for_stmt':
        return value

    return {
        # 'not': 'not not',
        'not': '',
        'is': 'is not',
    # this will cause "is not not" sometimes, so there's a hack to fix that later
        'in': 'not in',
        'break': 'continue',
        'continue': 'break',
        'True': 'False',
        'False': 'True',
    }.get(value, value)


def operator_mutation(value, context, **_):
    if context.stack[-2].type in ('import_from', 'param'):
        return value

    return {
        '+': '-',
        '-': '+',
        '*': '/',
        '/': '*',
        '//': '/',
        '%': '/',
        '<<': '>>',
        '>>': '<<',
        '&': '|',
        '|': '&',
        '^': '&',
        '**': '*',
        '~': '',

        '+=': '-=',
        '-=': '+=',
        '*=': '/=',
        '/=': '*=',
        '//=': '/=',
        '%=': '/=',
        '<<=': '>>=',
        '>>=': '<<=',
        '&=': '|=',
        '|=': '&=',
        '^=': '&=',
        '**=': '*=',
        '~=': '=',

        '<': '<=',
        '<=': '<',
        '>': '>=',
        '>=': '>',
        '==': '!=',
        '!=': '==',
        '<>': '==',
    }.get(value, value)


def and_or_test_mutation(children, node, **_):
    children = children[:]
    from parso.python.tree import Keyword
    children[1] = Keyword(
        value={'and': ' or', 'or': ' and'}[children[1].value],
        start_pos=node.start_pos,
    )
    return children


def expression_mutation(children, **_):
    def handle_assignment(children):
        if getattr(children[2], 'value', '---') != 'None':
            x = ' None'
        else:
            x = ' 7'
        children = children[:]
        children[2] = Name(value=x, start_pos=children[2].start_pos)

        return children

    if children[0].type == 'operator' and children[0].value == ':':
        if len(children) > 2 and children[2].value == '=':
            children[1:] = handle_assignment(children[1:])
    elif children[1].type == 'operator' and children[1].value == '=':
        children = handle_assignment(children)

    return children


def decorator_mutation(children, **_):
    assert children[-1].type == 'newline'
    return children[-1:]


def trailer_mutation(children, **_):
    if len(children) == 3 and children[0].type == 'operator' and \
            children[0].value == '[' and children[-1].type == 'operator' and \
            children[-1].value == ']' and \
            children[0].parent.type == 'trailer' and \
            children[1].type == 'name' and children[1].value != 'None':
        # Something that looks like "foo[bar]"
        return [children[0],
                Name(value='None', start_pos=children[0].start_pos),
                children[-1]]
    return children


def arglist_mutation(children, **_):
    if len(children) > 3 and children[0].type == 'name' and \
            children[0].value != 'None':
        return [Name(value='None',
                     start_pos=children[0].start_pos)] + children[1:]
    return children


mutations_by_type = {
    'operator': dict(value=operator_mutation),
    'keyword': dict(value=keyword_mutation),
    'number': dict(value=number_mutation),
    'name': dict(
        value=lambda value, **_: {
            'True': 'False',
            'False': 'True',
            'deepcopy': 'copy',
            # TODO: This breaks some tests, so should figure out why first: 'None': '0',
            # TODO: probably need to add a lot of things here... some builtins maybe, what more?
        }.get(value, value)),
    'string': dict(value=string_mutation),
    'argument': dict(children=argument_mutation),
    'or_test': dict(children=and_or_test_mutation),
    'and_test': dict(children=and_or_test_mutation),
    'lambdef': dict(children=lambda_mutation),
    'expr_stmt': dict(children=expression_mutation),
    'decorator': dict(children=decorator_mutation),
    'annassign': dict(children=expression_mutation),
    'trailer': dict(children=trailer_mutation),
    'arglist': dict(children=arglist_mutation),
}


# TODO: detect regexes and mutate them in nasty ways? Maybe mutate all strings as if they are regexes


class MutationContext(object):
    def __init__(self, source=None, mutate_id=ALL,
                 filename=None, exclude=lambda context: False, config=None):
        """

        :param source:

        :param mutate_id:
        :type mutate_id: tuple[str, int]

        :param filename:
        :type filename: str

        :param exclude:
        :param config:
        """
        self.index = 0
        self.source = source
        self.mutate_id = mutate_id
        self.number_of_performed_mutations = 0
        self.performed_mutation_ids = []
        assert isinstance(mutate_id, tuple)
        assert isinstance(mutate_id[0], str)
        assert isinstance(mutate_id[1], int)
        self.current_line_index = 0
        self.filename = filename
        self.exclude = exclude
        self.stack = []
        # TODO: refactor out?
        self.dict_synonyms = ['dict']
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None
        self.config = config

    def exclude_line(self):
        return self.current_line_index in self.pragma_no_mutate_lines or \
               self.exclude(context=self)

    @property
    def source_by_line_number(self):
        if self._source_by_line_number is None:
            self._source_by_line_number = self.source.split('\n')
        return self._source_by_line_number

    @property
    def current_source_line(self):
        return self.source_by_line_number[self.current_line_index]

    @property
    def mutate_id_of_current_index(self):
        return self.current_source_line, self.index

    @property
    def pragma_no_mutate_lines(self):
        if self._pragma_no_mutate_lines is None:
            self._pragma_no_mutate_lines = {
                i
                for i, line in enumerate(self.source_by_line_number)
                if
            '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[
                -1]
            }
        return self._pragma_no_mutate_lines

    def should_mutate(self):
        if self.mutate_id == ALL:
            return True

        return self.mutate_id in (ALL, self.mutate_id_of_current_index)


def mutate(context):
    """
    :type context: MutationContext
    :return: tuple: mutated source code, number of mutations performed
    :rtype: tuple[str, int]
    """
    try:
        result = parse(context.source, error_recovery=False)
    except Exception:
        print(
            'Failed to parse %s. Internal error from parso follows.' % context.filename)
        print('----------------------------------')
        raise

    mutate_list_of_nodes(result, context=context)
    mutated_source = result.get_code().replace(' not not ', ' ')

    if context.number_of_performed_mutations:
        # Check that if we said we mutated the code,
        # that it has actually changed
        assert context.source != mutated_source
    context.mutated_source = mutated_source
    return mutated_source, context.number_of_performed_mutations


def mutate_node(i, context):
    """
    :param context:
    :type context: MutationContext
    """
    context.stack.append(i)
    try:

        t = i.type

        if i.type == 'tfpdef':
            return

        if i.start_pos[0] - 1 != context.current_line_index:
            context.current_line_index = i.start_pos[0] - 1
            # indexes are unique per line, so start over here!
            context.index = 0

        if hasattr(i, 'children'):
            mutate_list_of_nodes(i, context=context)

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and context.mutate_id != ALL:
                return

        m = mutations_by_type.get(t)

        if m is None:
            return

        for key, value in sorted(m.items()):
            old = getattr(i, key)
            if context.exclude_line():
                continue

            new = evaluate(
                value,
                context=context,
                node=i,
                value=getattr(i, 'value', None),
                children=getattr(i, 'children', None),
            )
            assert not callable(new)
            if new != old:
                if context.should_mutate():
                    context.number_of_performed_mutations += 1
                    context.performed_mutation_ids.append(
                        context.mutate_id_of_current_index)
                    setattr(i, key, new)
                context.index += 1

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and \
                    context.mutate_id != ALL:
                return
    finally:
        context.stack.pop()


def mutate_list_of_nodes(result, context):
    """
    :type context: MutationContext
    """
    for i in result.children:

        # TODO: move to a filter?
        if i.type == 'name' and i.value in SKIP_NAMES:
            continue

        if i.type == 'operator' and i.value == '->':
            return

        mutate_node(i, context=context)

        # this is just an optimization to stop early
        if context.number_of_performed_mutations and context.mutate_id != ALL:
            return


def count_mutations(context):
    """
    :type context: MutationContext
    """
    assert context.mutate_id == ALL
    mutate(context)
    return context.number_of_performed_mutations


def list_mutations(context):
    """
    :type context: MutationContext

    :return: list of preformed mutation's ids
    :rtype: list[tuple[str, int]]
    """
    assert context.mutate_id == ALL
    mutate(context)
    return context.performed_mutation_ids


def mutate_file(backup, context):
    """

    :type backup: bool
    :type context: MutationContext

    :return: the number of mutations preformed
    :rtype: int
    """
    code = open(context.filename).read()
    context.source = code
    if backup:
        open(context.filename + '.bak', 'w').write(code)
    result, number_of_mutations_performed = mutate(context)
    with open(context.filename, 'w') as f:
        f.write(result)
    return number_of_mutations_performed
