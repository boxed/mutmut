"""Tests for enum class detection and handling."""

import libcst as cst

from mutmut.mutation.enum_mutation import ENUM_BASE_CLASSES
from mutmut.mutation.enum_mutation import is_enum_class
from mutmut.mutation.mutators import MethodType
from mutmut.mutation.mutators import get_method_type


class TestEnumBaseClasses:
    """Tests for ENUM_BASE_CLASSES constant."""

    def test_contains_standard_enum_types(self):
        assert "Enum" in ENUM_BASE_CLASSES
        assert "IntEnum" in ENUM_BASE_CLASSES
        assert "Flag" in ENUM_BASE_CLASSES
        assert "IntFlag" in ENUM_BASE_CLASSES
        assert "StrEnum" in ENUM_BASE_CLASSES

    def test_is_frozenset(self):
        assert isinstance(ENUM_BASE_CLASSES, frozenset)


class TestIsEnumClass:
    """Tests for is_enum_class function."""

    def test_simple_enum(self):
        code = "class Color(Enum): pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert is_enum_class(cls)

    def test_int_enum(self):
        code = "class Priority(IntEnum): pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert is_enum_class(cls)

    def test_flag_enum(self):
        code = "class Permission(Flag): pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert is_enum_class(cls)

    def test_attribute_access_enum(self):
        code = "class Status(enum.Enum): pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert is_enum_class(cls)

    def test_regular_class(self):
        code = "class MyClass: pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert not is_enum_class(cls)

    def test_class_with_other_base(self):
        code = "class MyClass(SomeBase): pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert not is_enum_class(cls)

    def test_class_with_multiple_bases(self):
        code = "class MyClass(Base1, Enum): pass"
        module = cst.parse_module(code)
        cls = module.body[0]
        assert is_enum_class(cls)


class TestGetMethodType:
    """Tests for get_method_type function."""

    def test_instance_method(self):
        code = """
class Foo:
    def method(self):
        pass
"""
        module = cst.parse_module(code)
        cls = module.body[0]
        method = cls.body.body[0]
        assert get_method_type(method) == MethodType.INSTANCE

    def test_staticmethod(self):
        code = """
class Foo:
    @staticmethod
    def method():
        pass
"""
        module = cst.parse_module(code)
        cls = module.body[0]
        method = cls.body.body[0]
        assert get_method_type(method) == MethodType.STATICMETHOD

    def test_classmethod(self):
        code = """
class Foo:
    @classmethod
    def method(cls):
        pass
"""
        module = cst.parse_module(code)
        cls = module.body[0]
        method = cls.body.body[0]
        assert get_method_type(method) == MethodType.CLASSMETHOD

    def test_other_single_decorator(self):
        code = """
class Foo:
    @property
    def method(self):
        pass
"""
        module = cst.parse_module(code)
        cls = module.body[0]
        method = cls.body.body[0]
        assert get_method_type(method) is None

    def test_multiple_decorators(self):
        code = """
class Foo:
    @staticmethod
    @some_decorator
    def method():
        pass
"""
        module = cst.parse_module(code)
        cls = module.body[0]
        method = cls.body.body[0]
        assert get_method_type(method) is None
