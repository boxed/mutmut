import json
import sys

from baron import parse, dumps, BaronError
from collections import defaultdict
from tri.declarative import evaluate

__version__ = '0.0.18'

ALL = 'all'


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
    context.current_line += value.count('\n')  # Advance line count!
    if value.startswith('"""') or value.startswith("'''"):
        return value  # We assume here that triple-quoted stuff are docs or other things that mutation is meaningless for
    return value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]


def call_argument_mutation(target, context, **_):
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
    def __init__(self, source=None, mutate_index=ALL, dict_synonyms=None, filename=None, exclude=lambda context: False, db_cursor=None):
        self.index = 0
        self._source = source
        self.mutate_index = mutate_index
        self.current_line = 1
        self.filename = filename
        self.exclude = exclude
        self.stack = []
        self.dict_synonyms = (dict_synonyms or []) + ['dict']
        self._source_by_line = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None
        self.surviving_mutants_by_line_number = defaultdict(int)
        self.performed_mutations_line_numbers = []
        self.performed_mutations = 0
        self.db_cursor = db_cursor

    def prepare_new_mutation(self):
        self.performed_mutations = 0
        self.performed_mutations_line_numbers = []
        self.current_line = 0
        self.index = 0

    def save_progress(self):
        if self.db_cursor:
            for line_number, surviving_mutants in self.surviving_mutants_by_line_number.items():
                if surviving_mutants == 0:
                    self.db_cursor.execute('INSERT INTO surviving_mutants (filename, path) VALUES (?, ?)', (self.path_by_line_number[line_number][0], json.dumps(self.path_by_line_number[line_number][1:])))

    @property
    def source(self):
        if self._source is None:
            self._source = open(self.filename).read()
        return self._source

    def exclude_line(self):
        return self.current_line in self.pragma_no_mutate_lines or self.exclude(context=self)

    @property
    def source_by_line_number(self):
        if self._source_by_line is None:
            self._source_by_line = self.source.split('\n')
        return self._source_by_line

    @property
    def path_by_line_number(self):
        """
        A "path" is a list of strings of all the increasing indent lines above the line in question.
        The first entry is the filename, and the last is the full line. An example is easier (comments
        are the paths for the line):

        ```
        def foo():         # ('file.py',                                  'def foo():')
            if a:          # ('file.py', 'def foo():',                    '    if a:')
                if b:      # ('file.py', 'def foo():', 'if a:',           '        if b:')
                    bar()  # ('file.py', 'def foo():', 'if a:',           '# foo')
                baz()      # ('file.py', 'def foo():', 'if a:', 'if b:',  '            bar()')
            quux()         # ('file.py', 'def foo():', 'if a:',           '        baz()')
        ```
        """
        if self._path_by_line is None:
            self._path_by_line = []
            stack = [self.filename]
            last_line = None
            last_indent = 0
            for l in self.source_by_line_number:
                stripped = l.strip(' \n "')
                if not stripped or stripped.startswith('#'):
                    self._path_by_line.append(tuple(stack) + (l,))
                    continue

                indent = count_indents(l)
                if indent > last_indent:
                    stack.append(last_line)
                elif indent < last_indent:
                    stack.pop(-1)

                self._path_by_line.append(tuple(stack) + (l,))

                last_line = l.strip()
                last_indent = count_indents(l)

            assert len(self._path_by_line) == len(self.source_by_line_number)
        return self._path_by_line

    @property
    def pragma_no_mutate_lines(self):
        if self._pragma_no_mutate_lines is None:
            self._pragma_no_mutate_lines = {
                i
                for i, line in enumerate(self.source_by_line_number)
                if '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[-1]
            }
        return self._pragma_no_mutate_lines


def count_indents(l):
    without = l.replace('\t', '    ').lstrip(' ')
    return len(l) - len(without)


def mutate(context):
    """
    :return: tuple: mutated source code, number of mutations performed
    """
    context.prepare_new_mutation()
    try:
        result = parse(context.source)
    except BaronError:
        print('Failed to parse %s. Internal error from baron follows, please report this to the baron project at https://github.com/PyCQA/baron/issues!' % context.filename)
        print('----------------------------------')
        raise
    mutate_list_of_nodes(result, context=context)
    mutated_source = dumps(result).replace(' not not ', ' ')
    if context.performed_mutations:
        assert context.source != mutated_source
    context.mutated_source = mutated_source
    return mutated_source, context.performed_mutations


def mutate_node(i, context):
    if not i:
        return

    context.stack.append(i)
    try:

        t = i['type']

        if t == 'endl':
            context.current_line += 1

        assert t in mutations_by_type, (t, i.keys(), (dumps(i)), i)
        m = mutations_by_type[t]

        if 'replace_entire_node_with' in m:
            if context.exclude_line():
                return

            if context.mutate_index in (ALL, context.index):
                i.clear()
                for k, v in m['replace_entire_node_with'].items():
                    i[k] = v
                context.performed_mutations += 1
                context.performed_mutations_line_numbers.append(context.current_line)
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

            if context.performed_mutations and context.mutate_index != ALL:
                return

        for key, value in sorted(m.items()):
            old = i[key]
            if context.exclude_line():
                continue

            new = evaluate(value, context=context, node=i, **i)
            assert not callable(new)
            if new != old:
                if context.mutate_index in (ALL, context.index):
                    context.performed_mutations += 1
                    context.performed_mutations_line_numbers.append(context.current_line)
                    i[key] = new
                context.index += 1

            if context.performed_mutations and context.mutate_index != ALL:
                return
    finally:
        context.stack.pop()


def mutate_list_of_nodes(result, context):
    for i in result:
        mutate_node(i, context=context)

        if context.performed_mutations and context.mutate_index != ALL:
            return


def count_mutations(context):
    assert context.mutate_index == ALL
    return mutate(context)[1]


def mutate_file(backup, context):
    if backup:
        open(context.filename + '.bak', 'w').write(context.source)
    result, mutations_performed = mutate(context)
    open(context.filename, 'w').write(result)
    return mutations_performed
