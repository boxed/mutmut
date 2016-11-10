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
    'return': dict(type='yield'),
    'yield': dict(type='return'),
}

# ("and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except", "exec", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "not", "or", "pass", "print", "raise", "return", "try", "while", "with", "yield")

# TODO: detect regexes and mutate them in nasty ways?

# TODO:
# str
# unicode?
# number
# bool
# continue -> break
# break -> continue
# yield -> return

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


def mutate(source):
    return mutate_list_of_nodes(parse(source))

recurse = {'def'}
ignore = {'endl'}
mutate_and_recurse = {'return'}


def mutate_node(i):
    t = i['type']
    if t in ignore:
        return

    if t in recurse:
        mutate_list_of_nodes(i['value'])
    else:
        m = mutations_by_type[t]
        for key, vale in m.items():
            i[key] = evaluate(m[key], node=i, **i)
            if t in mutate_and_recurse:
                mutate_node(i['value'])


def mutate_list_of_nodes(result):
    for i in result:
        mutate_node(i)

    return dumps(result)
