# import numpy
from copy import deepcopy

from baron import parse, dumps
from tri.declarative import evaluate

__version__ = '0.0.1'

ALL = 'all'


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


def float_exponant_mutation(value, **_):
    a, b = value.upper().split('E')
    return '%s-%s' % (a, (int(b) if b else 0) + 1)


def complex_mutation(value, **_):
    if '.' in value:
        return '%sj' % (float(value[:-1])+1)
    else:
        return '%sj' % (int(value[:-1])+1)


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
    'string': dict(value=lambda value, **_: value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]),
    'unicode_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'unicode_raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'binary_raw_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'complex': dict(value=complex_mutation),
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
    'ellipsis': {},
    'argument_generator_comprehension': {},
    'float_exponant_complex': {},  # TODO
    'yield_atom': {},
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
    'yield_atom': ['value'],
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