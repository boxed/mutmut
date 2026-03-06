"""Enum class detection and method type classification for mutation handling."""

import libcst as cst

# Known enum base class names from the standard library
ENUM_BASE_CLASSES = frozenset({"Enum", "IntEnum", "Flag", "IntFlag", "StrEnum"})


def is_enum_class(node: cst.ClassDef) -> bool:
    """Check if a ClassDef inherits from any known enum base class.

    Works for:
        - class Color(Enum): ...
        - class Permission(Flag): ...
        - class Status(enum.Enum): ...  (Attribute access)

    Limitations:
        - Cannot detect aliased imports: from enum import Enum as E
        - Cannot detect custom enum base classes
    """
    for base_arg in node.bases:
        base = base_arg.value

        # Case 1: Simple name like `Enum`, `Flag`, `IntEnum`
        if isinstance(base, cst.Name):
            if base.value in ENUM_BASE_CLASSES:
                return True

        # Case 2: Attribute access like `enum.Enum`, `enum.Flag`
        elif isinstance(base, cst.Attribute):
            if isinstance(base.attr, cst.Name) and base.attr.value in ENUM_BASE_CLASSES:
                return True

    return False
