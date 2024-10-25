from io import StringIO

import pytest
from parso import parse

from mutmut.__main__ import (
    CLASS_NAME_SEPARATOR,
    FuncContext,
    get_diff_for_mutant,
    is_generator,
    mangle_function_name,
    orig_function_and_class_names_from_key,
    pragma_no_mutate_lines,
    write_all_mutants_to_file,
    yield_mutants_for_module,
    yield_mutants_for_node,
)


@pytest.mark.parametrize(
    'original, expected', [
        ('foo(a, *args, **kwargs)', [
            'foo( *args, **kwargs)',
            'foo(None, *args, **kwargs)',
            'foo(a, **kwargs)',
            'foo(a, *args,)',
        ]),
        # TODO: Fix these
        # ('break', 'continue'),  # probably a bad idea. Can introduce infinite loops.
        ('a(b)', 'a(None)'),
        # ("x if a else b", "x if a else b"),
        ("dict(a=None)", ["dict(aXX=None)"]),
        ("dict(a=b)", ["dict(aXX=b)", 'dict(a=None)']),
        ('lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=False)))', [
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(show=True)))',
            'lambda **kwargs: Variable.integer(**setdefaults(kwargs, dict(showXX=False)))',
            'lambda **kwargs: Variable.integer(**setdefaults(None, dict(show=False)))',
            'lambda **kwargs: Variable.integer(**setdefaults( dict(show=False)))',
            # TODO: this mutant should exist... I guess we need to handle method calls separately from function calls?
            # 'lambda **kwargs: Variable.integer()',
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
        ("'''foo'''", []),  # don't mutate things we assume to be docstrings
        ("r'''foo'''", []),  # don't mutate things we assume to be docstrings
        ('(x for x in [])', []),  # don't mutate 'in' in generators
        ("DictSynonym(a=b)", ["DictSynonym(aXX=b)", 'DictSynonym(a=None)']),
        ("NotADictSynonym(a=b)", "NotADictSynonym(a=None)"),
        ('from foo import *', []),
        ('from .foo import *', []),
        ('import foo', []),
        ('import foo as bar', []),
        ('foo.bar', []),
        ('for x in y: pass', []),
        ('def foo(a, *args, **kwargs): pass', []),
        ('import foo', []),
        ('isinstance(a, b)', []),
        ('len(a)', []),
    ]
)
def test_basic_mutations(original, expected):
    if isinstance(expected, str):
        expected = [expected]
    func_node = parse(f'def fake():\n    {original}').children[0]
    node = func_node.children[-1]
    assert node.get_code().strip() == original.strip()
    mutants = list(yield_mutants_for_node(func_node=func_node, context=FuncContext(dict_synonyms={'DictSynonym'}), node=node))
    actual = sorted([
        parse(mutant).children[0].children[-1].get_code().strip()
        for (type_, mutant, _, _) in mutants
        if type_ == 'mutant'
    ])
    expected = sorted(expected)
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
        print(m)  # pragma: no cover

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
    assert mutants[0] == f'    def x{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}member__mutmut_1(self):        \n        return 2'


def mutants_for_source(source):
    no_mutate_lines = pragma_no_mutate_lines(source)
    r = []
    for type_, x, name_and_hash, mutant_name in yield_mutants_for_module(parse(source, error_recovery=False), no_mutate_lines):
        if type_ == 'mutant':
            r.append(x)
    return r


def full_mutated_source(source):
    no_mutate_lines = pragma_no_mutate_lines(source)
    r = []
    for type_, x, name_and_hash, mutant_name in yield_mutants_for_module(parse(source, error_recovery=False), no_mutate_lines):
        r.append(x)
    return '\n'.join(r).strip()


def test_function_with_annotation():
    source = "def capitalize(s : str):\n    return s[0].upper() + s[1:] if s else s\n".strip()
    mutants = mutants_for_source(source)
    assert mutants == [
        'def x_capitalize__mutmut_1(s : str):\n    return s[1].upper() + s[1:] if s else s',
        'def x_capitalize__mutmut_2(s : str):\n    return s[None].upper() + s[1:] if s else s',
        'def x_capitalize__mutmut_3(s : str):\n    return s[0].upper() - s[1:] if s else s',
        'def x_capitalize__mutmut_4(s : str):\n    return s[0].upper() + s[2:] if s else s',
        'def x_capitalize__mutmut_5(s : str):\n    return s[0].upper() + s[None] if s else s'
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
        '\ndef x_foo__mutmut_1():    \n    dict(a=None, c=d)\n',
        '\ndef x_foo__mutmut_2():    \n    dict(aXX=b, c=d)\n',
        '\ndef x_foo__mutmut_3():    \n    dict(a=b, c=None)\n',
        '\ndef x_foo__mutmut_4():    \n    dict(a=b, cXX=d)\n',
        '\ndef x_foo__mutmut_5():    \n    dict( c=d)\n',
        '\ndef x_foo__mutmut_6():    \n    dict(a=b,)\n',
    ]


def test_syntax_error():
    with pytest.raises(Exception):
        mutants_for_source(':!')


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
def wrapper():
    class ConfigurationOptions(Protocol):
        min_name_length: int
    """.strip()
    assert mutants_for_source(source) == []


def test_bug_github_issue_30():
    source = """
def wrapper():
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


def test_orig_function_name_from_key():
    assert orig_function_and_class_names_from_key(f'_{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}bar__mutmut_1') == ('bar', 'Foo')
    assert orig_function_and_class_names_from_key('x_bar__mutmut_1') == ('bar', None)


def test_mangle_function_name():
    assert mangle_function_name(name='bar', class_name=None) == 'x_bar'
    assert mangle_function_name(name='bar', class_name='Foo') == f'x{CLASS_NAME_SEPARATOR}Foo{CLASS_NAME_SEPARATOR}bar'


def test_diff_ops():
    source = """
def foo():    
    return 1


class Foo:
    def member(self):        
        return 3

    """.strip()

    out = StringIO()
    mutant_names, hash_by_function_name = write_all_mutants_to_file(out=out, source=source, filename='filename')
    assert len(mutant_names) == 2
    mutants_source = out.getvalue()

    diff1 = get_diff_for_mutant(mutant_name=mutant_names[0], source=mutants_source, path='test.py').strip()
    diff2 = get_diff_for_mutant(mutant_name=mutant_names[1], source=mutants_source, path='test.py').strip()

    assert diff1 == '''
--- test.py
+++ test.py
@@ -1,2 +1,2 @@
 def foo():    
-    return 1
+    return 2
'''.strip()

    assert diff2 == '''
--- test.py
+++ test.py
@@ -1,2 +1,2 @@
 def member(self):        
-        return 3
+        return 4
'''.strip()


def test_from_future_still_first():
    source = """
from __future__ import annotations
from collections.abc import Iterable

def foo():
    return 1
""".strip()
    mutated_source = full_mutated_source(source)
    assert mutated_source.split('\n')[0] == 'from __future__ import annotations'
    assert mutated_source.count('from __future__') == 1


def test_preserve_generators():
    source = '''
    def foo():
        yield 1
    '''.strip()
    mutated_source = full_mutated_source(source)
    assert 'yield from _mutmut_yield_from_trampoline' in mutated_source


def test_is_generator():
    source = '''
    def foo():
        yield 1
    '''.strip()
    assert is_generator(parse(source).children[0])

    source = '''
    def foo():
        yield from bar()
    '''.strip()
    assert is_generator(parse(source).children[0])

    source = '''
    def foo():
        return 1
    '''.strip()
    assert not is_generator(parse(source).children[0])

    source = '''
    def foo():
        def bar():
            yield 2
        return 1
    '''.strip()
    assert not is_generator(parse(source).children[0])


# def test_decorated_functions_mutation():
#     source = """
# @decorator
# def foo():
#     return 1
#     """.strip()
#
#     mutants = mutants_for_source(source)
#     assert len(mutants) == 1
