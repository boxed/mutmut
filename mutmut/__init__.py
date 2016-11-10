import numpy
from baron import parse, dumps
from tri.declarative import evaluate

__version__ = '0.0.1'

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
    'int': dict(value=lambda value, **_: str(int(value) + 1)),
    'float': dict(value=lambda value, **_: repr(numpy.nextafter(float(value), float(value) + 1000.0))),  # this might be a bit brutal :P
    'return': dict(type='yield'),
    'yield': dict(type='return'),
    'name': dict(
        value=lambda value, **_: {
            'True': 'False',
            'False': 'True',
        }[value]),
}

# ("and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except", "exec", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "not", "or", "pass", "print", "raise", "return", "try", "while", "with", "yield")

# TODO: detect regexes and mutate them in nasty ways?

# TODO:
# str
# unicode?
# long?
# continue -> break
# break -> continue

# compare_mapping = {
#     ast.Eq: ast.NotEq,
#     ast.NotEq: ast.Eq,
#     ast.Gt: ast.LtE,
#     ast.GtE: ast.Lt,
#     ast.Lt: ast.GtE,
#     ast.LtE: ast.Gt,
#     ast.In: ast.NotIn,
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
mutate_and_recurse = {'return'}


def mutate_node(i, context):
    t = i['type']
    if t in ignore:
        return

    if t in recurse:
        mutate_list_of_nodes(i['value'], context=context)
    else:
        m = mutations_by_type[t]
        for key, vale in m.items():
            if context.mutate_index in (None, context.index):
                context.performed_mutations += 1
                i[key] = evaluate(m[key], node=i, **i)
            context.index += 1
            if t in mutate_and_recurse:
                mutate_node(i['value'], context=context)


def mutate_list_of_nodes(result, context):
    for i in result:
        mutate_node(i, context=context)


def count_mutations(source):
    return mutate(source)[1]
