import sys

from parso import parse
from tri.declarative import evaluate

__version__ = '0.0.19'

ALL = ('all', -1)


if sys.version_info < (3, 0):
    text_types = (str, unicode)
else:
    text_types = (str,)


def int_mutation(value, **_):
    suffix = ''
    if value.upper().endswith('L'):
        value = value[:-1]
        suffix = 'L'

    if value.startswith('0o'):
        base = 8
        value = value[2:]
    elif value.startswith('0x'):
        base = 16
        value = value[2:]
    elif value.startswith('0b'):
        base = 2
        value = value[2:]
    elif value.startswith('0') and len(value) > 1:
        base = 8
        value = value[1:]
    else:
        base = 10

    result = repr(int(value, base=base) + 1)
    if not result.endswith(suffix):
        result += suffix
    return result


def number_mutation(value, **_):
    suffix = ''
    if value.upper().endswith('L'):
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
    elif value.startswith('0') and len(value) > 1:
        base = 8
        value = value[1:]
    else:
        base = 10

    if '.' in value:
        assert base == 10
        parsed = float(value)
    else:
        parsed = int(value, base=base)

    result = repr(parsed + 1)
    if not result.endswith(suffix):
        result += suffix
    return result


def comparison_mutation(first, **_):
    return {
        '<': '<=',
        '<=': '<',
        '>': '>=',
        '>=': '>',
        '==': '!=',
        '!=': '==',
        '<>': '==',
        'in': 'not in',
        'not': '',
        'is': 'is not',  # this will cause "is not not" sometimes, so there's a hack to fix that later
    }[first]


def float_exponant_mutation(value, **_):
    a, b = value.lower().split('e')
    return '%se%s' % (a, (int(b) if b else 0) + 1)


def complex_mutation(value, **_):
    if '.' in value:
        return '%sj' % (float(value[:-1])+1)
    else:
        return '%sj' % (int(value[:-1])+1)


def string_mutation(value, context, **_):
    """

    :type context: Context
    """
    prefix = value[:min([x for x in [value.find('"'), value.find("'")] if x != -1])]
    value = value[len(prefix):]

    context.current_line_index += value.count('\n')  # Advance line count!
    context.index = 0  # indexes are unique per line, so start over here!
    if value.startswith('"""') or value.startswith("'''"):
        return value  # We assume here that triple-quoted stuff are docs or other things that mutation is meaningless for
    return prefix + value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]


def call_argument_mutation(target, context, **_):
    """

    :type context: Context
    """
    if context.stack[-2]['type'] == 'call' and context.stack[-3]['value'][0]['type'] == 'name' and context.stack[-3]['value'][0]['value'] in context.dict_synonyms and 'value' in target:
        target = target.copy()
        target['value'] += 'XX'
        return target
    else:
        return target


def lambda_mutation(children, context, **_):
    from parso.python.tree import Name
    if len(children) != 4 or getattr(children[-1], 'value', '---') != 'None':
        return children[:3] + [Name(value=' None', start_pos=children[0].start_pos)]
    else:
        return children[:3] + [Name(value=' 0', start_pos=children[0].start_pos)]


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}


def assignment_mutation(value, **_):
    if 'value' in value and value['value'] == 'None':
        return {'section': 'number', 'type': 'int', 'value': '7'}
    else:
        return {'type': 'name', 'value': 'None'}


def argument_mutation(children, context, **_):
    """

    :type context: Context
    """
    if context.stack[-3].type == 'power':
        stack_pos_of_power_node = -3
    elif context.stack[-4].type == 'power':
        stack_pos_of_power_node = -4
    else:
        stack_pos_of_power_node = None

    if stack_pos_of_power_node and context.stack[stack_pos_of_power_node].children[0].type == 'name' and context.stack[stack_pos_of_power_node].children[0].value in context.dict_synonyms:
        children = children[:]
        from parso.python.tree import Name
        c = children[0]
        children[0] = Name(c.value + 'XX', start_pos=c.start_pos, prefix=c.prefix)

    return children


def keyword_mutation(value, context, **_):

    if context.stack[-2].type == 'comp_op' and value in ('in', 'is'):
        return value

    return {
        # 'not': 'not not',
        'not': '',
        'is': 'is not',  # this will cause "is not not" sometimes, so there's a hack to fix that later
        'in': 'not in',
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
        '<': '<=',
        '<=': '<',
        '>': '>=',
        '>=': '>',
        '==': '!=',
        '!=': '==',
        '<>': '==',

        # Don't mutate
        '(': '(',
        ')': ')',
        ',': ',',
        '[': '[',
        ']': ']',
        ':': ':',
        '=': '=',
        '{': '{',
        '}': '}',
        '.': '.',
        '@': '@',
    }[value]


def and_or_test_mutation(children, node, **_):
    children = children[:]
    from parso.python.tree import Keyword
    children[1] = Keyword(
        value={'and': ' or', 'or': ' and'}[children[1].value],
        start_pos=node.start_pos,
    )
    return children


def expression_mutation(children, **_):
    assert children[1].type == 'operator'
    if children[1].value == '=':
        if getattr(children[2], 'value', '---') != 'None':
            x = ' None'
        else:
            x = ' 7'
        children = children[:]
        from parso.python.tree import Name
        children[2] = Name(value=x, start_pos=children[2].start_pos)

    return children


mutations_by_type = {
    'operator': dict(
        value=operator_mutation,
    ),
    'keyword': dict(
        value=keyword_mutation,
    ),
    'number': dict(value=number_mutation),
    'name': dict(
        value=lambda value, **_: {
            'True': 'False',
            'False': 'True',
            'deepcopy': 'copy',
            # TODO: probably need to add a lot of things here... None, some builtins maybe, what more?
        }.get(value, value)),
    'string': dict(value=string_mutation),
    'argument': dict(children=argument_mutation),
    'or_test': dict(children=and_or_test_mutation),  # TODO: !!
    'and_test': {},  # TODO: !!
    'lambdef': dict(children=lambda_mutation),
    'expr_stmt': dict(children=expression_mutation),

    # Don't mutate
    'comp_op': {},  # things like "not in"
    'arith_expr': {},
    'endmarker': {},
    'term': {},
    'comparison': {},
    'atom': {},
    'testlist_comp': {},
    'power': {},
    'trailer': {},
    'subscript': {},
    'test': {},
    'import_from': {},
    'dictorsetmaker': {},  # TODO: ?
}

mutations_by_type_old = {
    'operator': dict(
        value=lambda value, **_: {
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
        }[value],
    ),
    'unitary_operator': dict(
        value=lambda value, **_: {
            'not': 'not not',
            '-': '+',
            '+': '-',
            '~': '',
        }[value],
    ),
    'int': dict(value=int_mutation),
    'long': dict(value=int_mutation),
    'octa': dict(value=int_mutation),
    'hexa': dict(value=int_mutation),
    'binary': dict(value=int_mutation),
    # 'float': dict(value=lambda value, **_: repr(numpy.nextafter(float(value), float(value) + 1000.0))),  # this might be a bit brutal :P
    'float': dict(value=lambda value, **_: repr(float(value) + 100.0)),
    'float_exponant': dict(value=float_exponant_mutation),
    'string': dict(value=string_mutation),
    'unicode_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'unicode_raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'complex': dict(value=complex_mutation),
    'continue': dict(type='break'),
    'break': dict(type='continue'),
    'name': dict(
        value=lambda value, **_: {
            'True': 'False',
            'False': 'True',
            'deepcopy': 'copy',
            # TODO: probably need to add a lot of things here... None, some builtins maybe, what more?
        }.get(value, value)),
    'comparison_operator': dict(
        first=comparison_mutation,
    ),
    'boolean_operator': dict(
        value=lambda value, **_: {
            'or': 'and',
            'and': 'or',
        }[value],
    ),
    'decorator': dict(replace_entire_node_with=NEWLINE),
    'call_argument': dict(target=call_argument_mutation),
    'lambda': dict(value=lambda_mutation),
    'assignment': dict(value=assignment_mutation),

    # Don't mutate:
    'tuple': {},
    'list': {},
    'dict': {},
    'set': {},
    'comma': {},
    'from_import': {},
    'import': {},
    'ifelseblock': {},
    'if': {},
    'elif': {},
    'else': {},
    'atomtrailers': {},  # http://redbaron.readthedocs.io/en/latest/nodes_reference.html#atomtrailersnode
    'dict_comprehension': {},
    'list_comprehension': {},
    'set_comprehension': {},
    'generator_comprehension': {},
    'comprehension_loop': {},
    'comprehension_if': {},
    'dictitem': {},
    'for': {},
    'try': {},
    'finally': {},
    'while': {},
    'class': {},
    'comment': {},
    'del': {},
    'assert': {},
    'raise': {},
    'dotted_name': {},
    'global': {},
    'print': {},
    'ternary_operator': {},
    'call': {},
    'def_argument': {},
    'dict_argument': {},
    'with': {},
    'with_context_item': {},
    'associative_parenthesis': {},
    'left_parenthesis': {},
    'right_parenthesis': {},
    'pass': {},
    'semicolon': {},
    'string_chain': {},
    'exec': {},
    'endl': {},
    'def': {},
    'getitem': {},
    'slice': {},
    'dot': {},
    'list_argument': {},
    'ellipsis': {},
    'argument_generator_comprehension': {},
    'float_exponant_complex': {},  # TODO
    'yield_atom': {},
    'space': {},
    'name_as_name': {},
    'dotted_as_name': {},
    'comparison': {},
    'except': {},
    'star': {},
    'return': {},  # TODO: we should mutate "return foo" -> "return None"
    'yield': {},  # TODO: we should mutate "yield foo" -> "yield None"
}

# TODO: detect regexes and mutate them in nasty ways? Maybe mutate all strings as if they are regexes


class Context(object):
    def __init__(self, source=None, mutate_id=ALL, dict_synonyms=None, filename=None, exclude=lambda context: False):
        self.index = 0
        self.source = source
        self.mutate_id = mutate_id
        self.number_of_performed_mutations = 0
        self.performed_mutation_ids = []
        assert isinstance(mutate_id, tuple)
        assert isinstance(mutate_id[0], text_types)
        assert isinstance(mutate_id[1], int)
        self.current_line_index = 0
        self.filename = filename
        self.exclude = exclude
        self.stack = []
        self.dict_synonyms = (dict_synonyms or []) + ['dict']
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None

    def exclude_line(self):
        return self.current_line_index in self.pragma_no_mutate_lines or self.exclude(context=self)

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
                if '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[-1]
            }
        return self._pragma_no_mutate_lines

    def should_mutate(self):
        if self.mutate_id == ALL:
            return True

        return self.mutate_id in (ALL, self.mutate_id_of_current_index)


def count_indents(l):
    without = l.replace('\t', '    ').lstrip(' ')
    return len(l) - len(without)


def mutate(context):
    """
    :type context: Context
    :return: tuple: mutated source code, number of mutations performed
    """
    try:
        result = parse(context.source)
    except Exception:
        print('Failed to parse %s. Internal error from parso follows.' % context.filename)
        print('----------------------------------')
        raise
    mutate_list_of_nodes(result, context=context)
    mutated_source = result.get_code().replace(' not not ', ' ')
    if context.number_of_performed_mutations:
        # Check that if we said we mutated the code, that it has actually changed
        assert context.source != mutated_source
    context.mutated_source = mutated_source
    return mutated_source, context.number_of_performed_mutations


def mutate_node(i, context):
    """
    :type context: Context
    """
    if not i:
        return

    context.stack.append(i)
    try:

        t = i.type

        # import pytest; pytest.set_trace()

        if t == 'endl':
            context.current_line_index += 1
            context.index = 0  # indexes are unique per line, so start over here!

        # TODO:
        # assert t in mutations_by_type, (t, (i.get_code()), i)
        # m = mutations_by_type[t]
        m = mutations_by_type.get(t, {})

        if 'replace_entire_node_with' in m:
            if context.exclude_line():
                return

            if context.should_mutate():
                i.clear()
                for k, v in m['replace_entire_node_with'].items():
                    i[k] = v
                context.number_of_performed_mutations += 1
                context.performed_mutation_ids.append(context.mutate_id_of_current_index)
            context.index += 1
            return

        if hasattr(i, 'children'):
            mutate_list_of_nodes(i, context=context)

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and context.mutate_id != ALL:
                return

        if m == {}:
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
                    context.performed_mutation_ids.append(context.mutate_id_of_current_index)
                    setattr(i, key, new)
                context.index += 1

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and context.mutate_id != ALL:
                return
    finally:
        context.stack.pop()


def mutate_list_of_nodes(result, context):
    """
    :type context: Context
    """
    for i in result.children:
        mutate_node(i, context=context)

        # this is just an optimization to stop early
        if context.number_of_performed_mutations and context.mutate_id != ALL:
            return


def count_mutations(context):
    """
    :type context: Context
    """
    assert context.mutate_id == ALL
    mutate(context)
    return context.number_of_performed_mutations


def list_mutations(context):
    """
    :type context: Context
    """
    assert context.mutate_id == ALL
    mutate(context)
    return context.performed_mutation_ids


def mutate_file(backup, context):
    """

    :type backup: bool
    :type context: Context
    """
    code = open(context.filename).read()
    context.source = code
    if backup:
        open(context.filename + '.bak', 'w').write(code)
    result, number_of_mutations_performed = mutate(context)
    with open(context.filename, 'w') as f:
        f.write(result)
    return number_of_mutations_performed
