# import numpy
from baron import parse, dumps
from tri.declarative import evaluate

__version__ = '0.0.1'

ALL = 'all'


def comparison_mutation(value, **_):
    value['first'] = {
        '<': '<=',
        '<=': '<',
        '>': '>=',
        '>=': '>',
        '==': '!=',
        '!=': '==',
        'in': 'not in',
        'not': '',
        'is': 'is not',  # this will cause "is not not" sometimes, so there's a hack to fix that later
    }[value['first']]
    return value


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
        }[value],
    ),
    'int': dict(value=lambda value, **_: repr(int(value) + 1)),
    'long': dict(value=lambda value, **_: repr(long(value) + 1)),
    # 'octa': dict(value=lambda value, **_: repr(long(value) + 1)),
    'hexa': dict(value=lambda value, **_: '0x%x' % (int(value[2:], base=16) + 1)),
    'binary': dict(value=lambda value, **_: '0b%x' % (int(value[2:], base=2) + 1)),
    # 'float': dict(value=lambda value, **_: repr(numpy.nextafter(float(value), float(value) + 1000.0))),  # this might be a bit brutal :P
    'float': dict(value=lambda value, **_: repr(float(value) + 100.0)),  # this might be a bit brutal :P
    'string': dict(value=lambda value, **_: value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]),
    'unicode_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
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
    'assignment': {},  # TODO
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
    return dumps(result).replace(' not not ', ' '), context.performed_mutations

recurse = {'def'}
ignore = {'endl'}
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
}


def mutate_node(i, context):
    if not i:
        return

    t = i['type']
    if t in ignore:
        return

    if t in recurse:
        mutate_list_of_nodes(i['value'], context=context)
    else:
        assert t in mutations_by_type, (t, i.keys())
        m = mutations_by_type[t]
        for key, vale in m.items():
            if context.mutate_index in (ALL, context.index):
                context.performed_mutations += 1
                i[key] = evaluate(m[key], node=i, **i)
            context.index += 1

        if t in mutate_and_recurse:
            for x in mutate_and_recurse[t]:
                if i[x] is None:
                    continue

                if isinstance(i[x], list):
                    mutate_list_of_nodes(i[x], context=context)
                else:
                    assert isinstance(i[x], dict), (i, type(i[x]), dumps(i))
                    mutate_node(i[x], context=context)


def mutate_list_of_nodes(result, context):
    for i in result:
        mutate_node(i, context=context)


def count_mutations(source):
    return mutate(source, ALL)[1]
