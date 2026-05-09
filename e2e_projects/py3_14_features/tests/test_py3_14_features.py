import annotationlib
import inspect
from py3_14_features import *

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

def test_point_move():
    point = Point(2, 3)
    moved_point = point.moved(5, 0)
    assert moved_point.x == 7
    assert moved_point.y == 3  # 3 + 0 == 3 - 0 == 3 -> not really tested

def test_point_from_tuple():
    point = Point.from_tuple((2, 2))
    # we don't test for x/y confusion
    assert point.x == 2
    assert point.y == 2

def test_point_from_tuple_classmethod():
    point = SubPoint.from_tuple_classmethod((2, 2))
    # we don't test for x/y confusion
    assert isinstance(point, SubPoint)
    assert point.x == 2
    assert point.y == 2
