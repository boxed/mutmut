import annotationlib
import inspect
from py3_14_features import get_len, get_foo_len_clone, get_foo_len, get_len_clone, Foo

def test_func_with_type_only_annotation():
    assert get_len([1, 2, 3]) == 3

def test_lazy_loaded_signature():
    assert get_foo_len(Foo(["abc", "def"])) == 2

def test_annotations():
    # the get_len trampoline should have the correct annotations
    assert annotationlib.get_annotations(get_len, format=annotationlib.Format.STRING) == {'data': 'Collection'}

    # 'Foo' should be available at this point, so we do not need the STRING format
    assert annotationlib.get_annotations(get_foo_len) == annotationlib.get_annotations(get_foo_len_clone)

def test_signature():
    # mutmut currently only achieves a stringified version, because we cannot eagerly evalute the signature
    assert inspect.signature(get_len, annotation_format=inspect.Format.STRING) == inspect.signature(get_len_clone, annotation_format=inspect.Format.STRING)

