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


def mutate(source, count_only=False):
    result = parse(source)
    mutation_count = mutate_list_of_nodes(result, count_only=count_only)
    if count_only:
        return mutation_count
    return dumps(result)

recurse = {'def'}
ignore = {'endl'}
mutate_and_recurse = {'return'}


def mutate_node(i, count_only=False):
    t = i['type']
    if t in ignore:
        return 0

    if t in recurse:
        return mutate_list_of_nodes(i['value'], count_only=count_only)
    else:
        m = mutations_by_type[t]
        mutation_count = 0
        for key, vale in m.items():
            mutation_count += 1
            if not count_only:
                i[key] = evaluate(m[key], node=i, **i)
            if t in mutate_and_recurse:
                mutation_count += mutate_node(i['value'], count_only=count_only)
        return mutation_count


def mutate_list_of_nodes(result, count_only=False):
    mutation_count = 0
    for i in result:
        mutation_count += mutate_node(i, count_only=count_only)

    return mutation_count


def count_mutations(source):
    return mutate(source, count_only=True)