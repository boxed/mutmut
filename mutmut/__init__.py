import numpy
from baron import parse, dumps
from tri.declarative import evaluate

__version__ = '0.0.1'


def comparison_mutation(value, **_):
    value['first'] = {
        '<': '<=',
        '<=': '<',
        '>': '>=',
        '>=': '>',
        '==': '!=',
        '!=': '==',
        'in': 'not in',
        'not in': 'in',
        'not': '',
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
        }[value],
    ),
    'int': dict(value=lambda value, **_: repr(int(value) + 1)),
    'long': dict(value=lambda value, **_: repr(long(value) + 1)),
    # 'octa': dict(value=lambda value, **_: repr(long(value) + 1)),
    'hexa': dict(value=lambda value, **_: '0x%x' % (int(value[2:], base=16) + 1)),
    'binary': dict(value=lambda value, **_: '0b%x' % (int(value[2:], base=2) + 1)),
    'float': dict(value=lambda value, **_: repr(numpy.nextafter(float(value), float(value) + 1000.0))),  # this might be a bit brutal :P
    'string': dict(value=lambda value, **_: value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]),
    'unicode_string': dict(value=lambda value, **_: value[0:2] + 'XX' + value[2:-1] + 'XX' + value[-1]),
    'return': dict(type='yield'),
    'yield': dict(type='return'),
    'raise': dict(type='return'),
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

    # Don't mutate:
    'tuple': dict(),
    'list': dict(),
    'dict': dict(),
    'set': dict(),
    'comma': dict(),
    'from_import': dict(),
    'import': dict(),
    'assignment': dict(),  # TODO
    'ifelseblock': dict(),
    'if': dict(),
    'elif': dict(),
    'else': dict(),
    'atomtrailers': dict(),  # http://redbaron.readthedocs.io/en/latest/nodes_reference.html#atomtrailersnode
    'dict_comprehension': {},
    'list_comprehension': {},
    'set_comprehension': {},
    'comprehension_loop': {},
    'comprehension_if': {},
    'dictitem': {},
    'for': {},
    'try': {},
    'class': {},
    'comment': {},
    'del': {},
    'assert': {},
}

# TODO: ("and", "as", "assert", "del", "elif", "else", "except", "exec", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "not", "or", "pass", "print", "raise", "try", "while", "with")

# TODO: detect regexes and mutate them in nasty ways?

# TODO:

# compare_mapping = {
#     ast.NotIn: ast.In,
#     ast.Is: ast.IsNot,
#     ast.IsNot: ast.Is
#     }


class Context(object):
    def __init__(self, mutate_index):
        self.index = 0
        self.performed_mutations = 0
        self.mutate_index = mutate_index


def mutate(source, mutate_index=None):
    """
    :param source: source code
    :param mutate_index: the index of the mutation to be performed, if None mutates all available places
    :return: tuple: mutated source code, number of mutations performed
    """
    result = parse(source)
    context = Context(mutate_index=mutate_index)
    mutate_list_of_nodes(result, context=context)
    return dumps(result), context.performed_mutations

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
    'comprehension_loop': ['ifs', 'iterator', 'target'],
    'unitary_operator': ['target'],
    'dictitem': ['key', 'value'],
    'for': ['else', 'iterator', 'target', 'value'],
    'raise': ['instance', 'value'],
    'try': ['else', 'finally', 'value'],
    'class': ['inherit_from', 'decorators', 'value'],
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
        assert t in mutations_by_type, t
        m = mutations_by_type[t]
        for key, vale in m.items():
            if context.mutate_index in (None, context.index):
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
                    assert isinstance(i[x], dict), type(i[x])
                    mutate_node(i[x], context=context)


def mutate_list_of_nodes(result, context):
    for i in result:
        mutate_node(i, context=context)


def count_mutations(source):
    return mutate(source)[1]
