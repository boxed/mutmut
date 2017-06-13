import sys
from baron import parse, dumps
from tri.declarative import evaluate, dispatch, Namespace

__version__ = '0.0.4'

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


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}

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

    # Don't mutate:
    'tuple': {},
    'list': {},
    'dict': {},
    'set': {},
    'comma': {},
    'from_import': {},
    'import': {},
    'assignment': {},
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
    'call_argument': {},
    'lambda': {},
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
    'return': {},  # TODO: we should mutate "return foo" -> "return None"
    'yield': {},  # TODO: we should mutate "yield foo" -> "yield None"
}

# TODO: detect regexes and mutate them in nasty ways? Maybe mutate all strings as if they are regexes


class Context(object):
    def __init__(self, mutate_index, filename=None, exclude=lambda context: False):
        self.index = 0
        self.performed_mutations = 0
        self.mutate_index = mutate_index
        self.current_line = 1
        self.pragma_no_mutate_lines = set()
        self.filename = filename
        self.exclude = exclude

    def exclude_line(self):
        return self.current_line in self.pragma_no_mutate_lines or self.exclude(context=self)


@dispatch(
    context=Namespace(),
)
def mutate(source, mutate_index, context):
    """
    :param source: source code
    :param mutate_index: the index of the mutation to be performed, if ALL mutates all available places
    :return: tuple: mutated source code, number of mutations performed
    """
    result = parse(source)
    context = Context(mutate_index=mutate_index, **context)
    context.pragma_no_mutate_lines = {i+1 for i, line in enumerate(source.split('\n')) if '# pragma: no mutate' in line}  # lines are 1 based indexed
    mutate_list_of_nodes(result, context=context)
    result_source = dumps(result).replace(' not not ', ' ')
    if context.performed_mutations:
        assert source != result_source
    return result_source, context.performed_mutations


def mutate_node(i, context):
    if not i:
        return

    t = i['type']

    if t == 'endl':
        context.current_line += 1

    assert t in mutations_by_type, (t, i.keys(), dumps(i))
    m = mutations_by_type[t]

    if 'replace_entire_node_with' in m:
        if context.mutate_index in (ALL, context.index):
            i.clear()
            for k, v in m['replace_entire_node_with'].items():
                i[k] = v
            context.performed_mutations += 1
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
                i[key] = new
            context.index += 1

        if context.performed_mutations and context.mutate_index != ALL:
            return


def mutate_list_of_nodes(result, context):
    for i in result:
        mutate_node(i, context=context)

        if context.performed_mutations and context.mutate_index != ALL:
            return


@dispatch(
    context=Namespace(),
)
def count_mutations(source, context):
    return mutate(source, ALL, context=context)[1]


@dispatch(
    context=Namespace(),
)
def mutate_file(backup, mutation, filename, context):  # pragma: no cover
    code = open(filename).read()
    if backup:
        open(filename + '.bak', 'w').write(code)
    context.filename = filename
    result, mutations_performed = mutate(code, mutation, context=context)
    open(filename, 'w').write(result)
    return mutations_performed
