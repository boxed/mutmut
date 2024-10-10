import pytest
from parso import parse

from mutmut import array_subscript_pattern, function_call_pattern, ASTPattern
from mutmut3 import (
    FuncContext,
    pragma_no_mutate_lines,
    yield_mutants_for_module,
    yield_mutants_for_node,
)


def test_matches_py3():
    node = parse('a: Optional[int] = 7\n').children[0].children[0].children[1].children[1].children[1].children[1]
    assert not array_subscript_pattern.matches(node=node)


def test_matches():
    node = parse('from foo import bar').children[0]
    assert not array_subscript_pattern.matches(node=node)
    assert not function_call_pattern.matches(node=node)
    assert not array_subscript_pattern.matches(node=node)
    assert not function_call_pattern.matches(node=node)

    node = parse('foo[bar]\n').children[0].children[0].children[1].children[1]
    assert array_subscript_pattern.matches(node=node)

    node = parse('foo(bar)\n').children[0].children[0].children[1].children[1]
    assert function_call_pattern.matches(node=node)


def test_ast_pattern_for_loop():
    p = ASTPattern(
        """
for x in y:
#   ^ n  ^ match
    pass
    # ^ x
""",
        x=dict(
            of_type='simple_stmt',
            marker_type='any',
        ),
        n=dict(
            marker_type='name',
        ),
        match=dict(
            marker_type='any',
        )
    )

    n = parse("""for a in [1, 2, 3]:
    if foo:
        continue
""").children[0].children[3]
    assert p.matches(node=n)

    n = parse("""for a, b in [1, 2, 3]:
    if foo:
        continue
""").children[0].children[3]
    assert p.matches(node=n)


@pytest.mark.parametrize(
    'original, expected', [
        # TODO: Fix these
        # ('break', 'continue'),  # probably a bad idea. Can introduce infinite loops.
        # ('a(b)', 'a(None)'),
        # ('s[x]', 's[None]'),
        # ("x if a else b", "x if a else b"),
        ("dict(a=b)", "dict(aXX=b)"),
        ('lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=False)))', [
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=True)))',
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(showXX=False)))',
            'lambda **kwargs: None',
        ]),
        ('a: Optional[int] = None', 'a: Optional[int] = ""'),
        ('a: int = 1', ['a: int = 2', 'a: int = None']),
        ('lambda: 0', ['lambda: 1', 'lambda: None']),
        ("1 in (1, 2)", ['2 in (1, 2)', '1 not in (1, 2)', '1 in (2, 2)', '1 in (1, 3)']),
        ('1+1', ['2+1', '1-1', '1+2']),
        ('1', '2'),
        ('1-1', ['2-1', '1+1', '1-2']),
        ('1*1', ['2*1', '1/1', '1*2']),
        ('1/1', ['2/1', '1*1', '1/2']),
        # ('1.0', '1.0000000000000002'),  # using numpy features
        ('1.0', '2.0'),
        ('0.1', '1.1'),
        ('1e-3', '1.001'),
        ('True', 'False'),
        ('False', 'True'),
        ('"foo"', '"XXfooXX"'),
        ("'foo'", "'XXfooXX'"),
        ("u'foo'", "u'XXfooXX'"),
        ("0", "1"),
        ("0o0", "1"),
        ("0.", "1.0"),
        ("0x0", "1"),
        ("0b0", "1"),
        ("1<2", ['2<2', '1<=2', '1<3']),
        ('(1, 2)', ['(2, 2)', '(1, 3)']),
        ("1 not in (1, 2)", ['2 not in (1, 2)', '1  in (1, 2)', '1 not in (2, 2)', '1 not in (1, 3)']),  # two spaces here because "not in" is two words
        ("foo is foo", "foo is not foo"),
        ("foo is not foo", "foo is  foo"),
        ('a or b', 'a and b'),
        ('a and b', 'a or b'),
        ('a = b', 'a = None'),
        ('a = b = c = x', 'a = b = c = None'),
        # subscript
        ('a[None]', []),
        ('a[b]', 'a[None]'),
        ('s[0]', ['s[1]', 's[None]']),
        ('s[0] = a', ['s[1] = a', 's[None] = a', 's[0] = None']),
        ('s[1:]', ['s[2:]', 's[None]']),

        ('1j', '2j'),
        ('1.0j', '2.0j'),
        ('0o1', '2'),
        ('1.0e10', '10000000001.0'),
        ('a = {x for x in y}', 'a = None'),
        ('x+=1', ['x=1', 'x-=1', 'x+=2']),
        ('x-=1', ['x=1', 'x+=1', 'x-=2']),
        ('x*=1', ['x=1', 'x/=1', 'x*=2']),
        ('x/=1', ['x=1', 'x*=1', 'x/=2']),
        ('x//=1', ['x=1', 'x/=1', 'x//=2']),
        ('x%=1', ['x=1', 'x/=1', 'x%=2']),
        ('x<<=1', ['x=1', 'x>>=1', 'x<<=2']),
        ('x>>=1', ['x=1', 'x<<=1', 'x>>=2']),
        ('x&=1', ['x=1', 'x|=1', 'x&=2']),
        ('x|=1', ['x=1', 'x&=1', 'x|=2']),
        ('x^=1', ['x=1', 'x&=1', 'x^=2']),
        ('x**=1', ['x=1', 'x*=1', 'x**=2']),
        ('def foo(s: Int = 1): pass', 'def foo(s: Int = 2): pass'),
        ('a = None', 'a = ""'),
        ('lambda **kwargs: None', 'lambda **kwargs: 0'),
        ('lambda: None', 'lambda: 0'),
        ('def foo(s: str): pass', []),
        ('def foo(a, *, b): pass', []),
        ('a(None)', []),
        ('foo(a, *args, **kwargs)', []),
        ("'''foo'''", []),  # don't mutate things we assume to be docstrings
        ("r'''foo'''", []),  # don't mutate things we assume to be docstrings
        ('(x for x in [])', []),  # don't mutate 'in' in generators
        ("DictSynonym(a=b)", "DictSynonym(aXX=b)"),
        ("NotADictSynonym(a=b)", []),
        ('from foo import *', []),
        ('from .foo import *', []),
        ('import foo', []),
        ('import foo as bar', []),
        ('foo.bar', []),
        ('for x in y: pass', []),
        ('def foo(a, *args, **kwargs): pass', []),
        ('import foo', []),
    ]
)
def test_basic_mutations(original, expected):
    if isinstance(expected, str):
        expected = [expected]
    func_node = parse(f'def fake():\n    {original}').children[0]
    node = func_node.children[-1]
    assert node.get_code().strip() == original.strip()
    mutants = list(yield_mutants_for_node(func_node=func_node, context=FuncContext(dict_synonyms={'DictSynonym'}), node=node))
    actual = [
        parse(mutant).children[0].children[-1].get_code().strip()
        for (type_, mutant, _, _) in mutants
        if type_ == 'mutant'
    ]
    assert actual == expected


def test_do_not_mutate_annotations():
    source = """
def foo() -> int:
    bar: Optional[int]
    return
    """.strip()

    mutants = [
        mutant
        for type_, mutant, _, _ in yield_mutants_for_module(parse(source), {})
        if type_ == 'mutant'
    ]
    for m in mutants:
        print(m)

    assert not mutants


def test_basic_class():
    source = """
class Foo:
    def member(self):        
        return 1
    """.strip()

    mutants = [
        mutant
        for type_, mutant, _, _ in yield_mutants_for_module(parse(source), {})
        if type_ == 'mutant'
    ]
    for m in mutants:
        print(m)

    assert len(mutants) == 1
    assert mutants[0] == '    def _Foo_member__mutmut_1(self):        \n        return 2'


def mutants_for_source(source):
    no_mutate_lines = pragma_no_mutate_lines(source)
    r = []
    for type_, x, name_and_hash, mutant_name in yield_mutants_for_module(parse(source, error_recovery=False), no_mutate_lines):
        if type_ == 'mutant':
            r.append(x)
    return r


def test_function_with_annotation():
    source = "def capitalize(s : str):\n    return s[0].upper() + s[1:] if s else s\n".strip()
    mutants = mutants_for_source(source)
    assert mutants == [
        'def capitalize__mutmut_1(s : str):\n    return s[1].upper() + s[1:] if s else s',
        'def capitalize__mutmut_2(s : str):\n    return s[None].upper() + s[1:] if s else s',
        'def capitalize__mutmut_3(s : str):\n    return s[0].upper() - s[1:] if s else s',
        'def capitalize__mutmut_4(s : str):\n    return s[0].upper() + s[2:] if s else s',
        'def capitalize__mutmut_5(s : str):\n    return s[0].upper() + s[None] if s else s'
    ]


def test_pragma_no_mutate():
    source = """def foo():\n    return 1+1  # pragma: no mutate\n""".strip()
    mutants = mutants_for_source(source)
    assert not mutants


def test_pragma_no_mutate_and_no_cover():
    source = """def foo():\n    return 1+1  # pragma: no cover, no mutate\n""".strip()
    mutants = mutants_for_source(source)
    assert not mutants


def test_mutate_dict():
    source = '''
def foo():    
    dict(a=b, c=d)
'''
    mutants = mutants_for_source(source)
    assert mutants == [
        '''
def foo__mutmut_1():    
    dict(aXX=b, c=d)
''',
'''
def foo__mutmut_2():    
    dict(a=b, cXX=d)
'''
    ]


def test_syntax_error():
    with pytest.raises(Exception):
        mutants_for_source(':!')

# TODO: this test becomes incorrect with the new mutation_id system, should try to salvage the idea though...
# def test_mutation_index():
#     source = '''
#
# a = b
# b = c + a
# d = 4 - 1
#
#
#     '''.strip()
#     num_mutations = count_mutations(Context(source=source))
#     mutants = [mutate(Context(source=source, mutation_id=i)) for i in range(num_mutations)]
#     assert len(mutants) == len(set(mutants))  # no two mutants should be the same
#
#     # invalid mutation index should not mutate anything
#     mutated_source, count = mutate(Context(source=source, mutation_id=num_mutations + 1))
#     assert mutated_source.strip() == source
#     assert count == 0


def test_bug_github_issue_18():
    source = """
@register.simple_tag(name='icon')
def icon(name):
    if name is None:
        return ''
    tpl = '<span class="glyphicon glyphicon-{}"></span>'
    return format_html(tpl, name)
    """.strip()
    mutants_for_source(source)


def test_bug_github_issue_19_argument_mutation_crash():
    source = """key = lambda a: "foo"
filters = dict((key(field), False) for field in fields)"""
    mutants_for_source(source)


def test_bug_github_issue_26():
    source = """
class ConfigurationOptions(Protocol):
    min_name_length: int
    """.strip()
    assert mutants_for_source(source) == []


def test_bug_github_issue_30():
    source = """
def from_checker(cls: Type['BaseVisitor'], checker) -> 'BaseVisitor':
    pass
    """.strip()
    assert mutants_for_source(source) == []


def test_bug_github_issue_77():
    # Don't crash on this
    assert mutants_for_source('') == []


def test_multiline_dunder_whitelist():
    source = """
__all__ = [
    1,
    2,
    'foo',
    'bar',
]
    """.strip()
    mutants = mutants_for_source(source)
    assert not mutants


def test_bad_mutation_str_type_definition():
    source = """
def foo():
    foo: 'SomeType'
""".strip()
    mutants = mutants_for_source(source)
    assert not mutants
