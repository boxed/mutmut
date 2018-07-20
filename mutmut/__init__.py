import sys

from baron import parse, dumps, BaronError
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
    context.current_line_index += value.count('\n')  # Advance line count!
    context.index = 0  # indexes are unique per line, so start over here!
    if value.startswith('"""') or value.startswith("'''"):
        return value  # We assume here that triple-quoted stuff are docs or other things that mutation is meaningless for
    return value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]


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


def lambda_mutation(value, **_):
    if (value.get('type'), value.get('value')) == ('name', 'None'):
        return {'section': 'number', 'type': 'int', 'value': '0'}
    else:
        return {'type': 'name', 'value': 'None'}


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}


def assignment_mutation(value, **_):
    if 'value' in value and value['value'] == 'None':
        return {'section': 'number', 'type': 'int', 'value': '7'}
    else:
        return {'type': 'name', 'value': 'None'}


mutations_by_type = {
    'binary_operator': dict(
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
    except BaronError:
        print('Failed to parse %s. Internal error from baron follows, please report this to the baron project at https://github.com/PyCQA/baron/issues!' % context.filename)
        print('----------------------------------')
        raise
    mutate_list_of_nodes(result, context=context)
    mutated_source = dumps(result).replace(' not not ', ' ')
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

        t = i['type']

        if t == 'endl':
            context.current_line_index += 1
            context.index = 0  # indexes are unique per line, so start over here!

        assert t in mutations_by_type, (t, i.keys(), (dumps(i)), i)
        m = mutations_by_type[t]

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

        for _, x in sorted(i.items()):
            if x is None:
                continue  # pragma: no cover

            if isinstance(x, list):
                if x:
                    mutate_list_of_nodes(x, context=context)
            elif isinstance(x, dict):
                mutate_node(x, context=context)
            else:
                assert isinstance(x, text_types + (bool,))

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and context.mutate_id != ALL:
                return

        for key, value in sorted(m.items()):
            old = i[key]
            if context.exclude_line():
                continue

            new = evaluate(value, context=context, node=i, **i)
            assert not callable(new)
            if new != old:
                if context.should_mutate():
                    context.number_of_performed_mutations += 1
                    context.performed_mutation_ids.append(context.mutate_id_of_current_index)
                    i[key] = new
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
    for i in result:
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
