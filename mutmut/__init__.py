# import numpy
from copy import deepcopy

from baron import parse, dumps
from tri.declarative import evaluate

__version__ = '0.0.1'

ALL = 'all'


def to_int(s, base=10):
    if s.upper().endswith('L'):
        s = s[:-1]
    if base == 8 and s.lower().startswith('o'):
        s = s[1:]

    return int(s, base=base)


def comparison_mutation(value, **_):
    result = deepcopy(value)
    result['first'] = {
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
    }[value['first']]
    return result


def float_exponent_mutation(value, **_):
    ASDASDASDSA


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
            '-': '',
            '~': '',
        }[value],
    ),
    'int': dict(value=lambda value, **_: repr(to_int(value) + 1)),
    'long': dict(value=lambda value, **_: repr(long(value) + 1)),
    'octa': dict(value=lambda value, **_: repr(to_int(value[1:], base=8) + 1)),
    'hexa': dict(value=lambda value, **_: '0x%x' % (to_int(value[2:], base=16) + 1)),
    'binary': dict(value=lambda value, **_: '0b%x' % (to_int(value[2:], base=2) + 1)),
    # 'float': dict(value=lambda value, **_: repr(numpy.nextafter(float(value), float(value) + 1000.0))),  # this might be a bit brutal :P
    'float': dict(value=lambda value, **_: repr(float(value) + 100.0)),  # this might be a bit brutal :P
    'float_exponent': dict(value=float_exponent_mutation),  # this might be a bit brutal :P
    'string': dict(value=lambda value, **_: value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]),
    'unicode_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'unicode_raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'return': dict(type='yield'),
    'yield': dict(type='return'),
    'continue': dict(type='break'),
    'break': dict(type='continue'),
    'name': dict(
        value=lambda value, **_: {
            'True': 'False',
            'False': 'True',
            # TODO: probably need to add a lot of things here... None, some builtins maybe, what more?
        }.get(value, value)),
    'comparison': dict(
        value=comparison_mutation,
    ),
    'boolean_operator': dict(
        value=lambda value, **_: {
            'or': 'and',
            'and': 'or',
        }[value],
    ),

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
    'decorator': {},
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
    'argument_generator_comprehension': {},
}

# TODO: detect regexes and mutate them in nasty ways?


class Context(object):
    def __init__(self, mutate_index):
        self.index = 0
        self.performed_mutations = 0
        self.mutate_index = mutate_index


def mutate(source, mutate_index):
    """
    :param source: source code
    :param mutate_index: the index of the mutation to be performed, if ALL mutates all available places
    :return: tuple: mutated source code, number of mutations performed
    """
    result = parse(source)
    context = Context(mutate_index=mutate_index)
    mutate_list_of_nodes(result, context=context)
    result_source = dumps(result).replace(' not not ', ' ')
    if context.performed_mutations:
        assert source != result_source
    return result_source, context.performed_mutations

mutate_and_recurse = {
    'return': ['value'],
    'tuple': ['value'],
    'list': ['value'],
    'set': ['value'],
    'dict': ['value'],
    'ifelseblock': ['value'],
    'if': ['value'],
    'comprehension_if': ['value'],
    'elif': ['value'],
    'else': ['value'],
    'binary_operator': ['first', 'second'],
    'comparison': ['first', 'second'],
    'dict_comprehension': ['generators', 'result'],
    'list_comprehension': ['generators', 'result'],
    'set_comprehension': ['generators', 'result'],
    'generator_comprehension': ['generators', 'result'],
    'comprehension_loop': ['ifs', 'iterator', 'target'],
    'unitary_operator': ['target'],
    'dictitem': ['key', 'value'],
    'for': ['else', 'iterator', 'target', 'value'],
    'raise': ['instance', 'value'],
    'try': ['else', 'finally', 'value'],
    'finally': ['value'],
    'class': ['inherit_from', 'decorators', 'value'],
    'decorator': ['value', 'call'],
    'print': ['value'],
    'ternary_operator': ['value', 'first', 'second'],
    'call': ['value'],
    'call_argument': ['value', 'target'],
    'lambda': ['value', 'arguments'],
    'def_argument': ['value', 'target'],
    'dict_argument': ['value'],
    'with': ['value', 'contexts'],
    'with_context_item': ['value', 'as'],
    'associative_parenthesis': ['value'],
    'boolean_operator': ['first', 'second'],
    'while': ['test', 'value', 'else'],
    'string_chain': ['value'],
    'exec': ['globals', 'locals', 'value'],
    'def': ['value'],
    'atomtrailers': ['value'],
    'getitem': ['value'],
    'assignment': ['value', 'target'],
    'slice': ['upper', 'step', 'lower'],
    'list_argument': ['value'],
    'argument_generator_comprehension': ['generators', 'result'],
}


def mutate_node(i, context):
    if not i:
        return

    t = i['type']
    # print 'mutate_node', context.index, i

    assert t in mutations_by_type, (t, i.keys(), dumps(i))
    m = mutations_by_type[t]

    if t in mutate_and_recurse:
        for x in mutate_and_recurse[t]:
            if i[x] is None:
                continue

            if isinstance(i[x], list):
                mutate_list_of_nodes(i[x], context=context)
            else:
                assert isinstance(i[x], dict), (i, type(i[x]), dumps(i))
                mutate_node(i[x], context=context)

            if context.performed_mutations and context.mutate_index != ALL:
                return

    for key, value in m.items():
        old = i[key]
        new = evaluate(value, node=i, **i)
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


def count_mutations(source):
    return mutate(source, ALL)[1]


def mutate_file(backup, mutation, filename):
    if backup:
        open(filename + '.bak', 'w').write(open(filename).read())
    result, mutations_performed = mutate(open(filename).read(), mutation)
    open(filename[0], 'w').write(result)
    return mutations_performed