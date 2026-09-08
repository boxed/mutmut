"""Splicing mutant text must produce exactly what rebuilding and rendering the tree produces."""

from pathlib import Path

import pytest

import mutmut.mutation.file_mutation
from mutmut.mutation.file_mutation import PrerenderedFunction
from mutmut.mutation.file_mutation import mutate_file_contents

CORPUS = sorted(path for path in (Path(__file__).parent.parent / "data" / "test_generation").glob("valid_*.py"))

EXTRA_SOURCES = {
    "methods_with_indented_blocks": """
class Greeter:
    \"\"\"A class whose methods contain blocks, decorators and multi-line expressions.\"\"\"

    @staticmethod
    def pick(items, key):
        if key in items:
            for item in items:
                if item == key:
                    return item
        else:
            return None

    @property
    def name(self):
        return (
            "a"
            + "b"
        )

    async def fetch(self, session, url="http://example.com"):
        async with session.get(url) as response:
            return await response.text()


def top_level(x, y=1):
    return x + y
""",
    "tabs_and_continuations": "def f(a,\n\t\tb):\n\tif a:\n\t\treturn a \\\n\t\t\t+ b\n\treturn b\n",
    "nested_class": "class A:\n    class B:\n        def m(self, x):\n            return x * 2\n\n    def n(self, y):\n        return y - 1\n",
}


def _both_implementations(monkeypatch, filename: str, source: str):
    assert mutmut.mutation.file_mutation.SPLICE_MUTANT_TEXT, "libcst internals unavailable: nothing to compare"
    spliced = mutate_file_contents(filename, source)
    monkeypatch.setattr(mutmut.mutation.file_mutation, "SPLICE_MUTANT_TEXT", False)
    rebuilt = mutate_file_contents(filename, source)
    return spliced, rebuilt


def _assert_identical(spliced, rebuilt):
    assert spliced.code == rebuilt.code
    assert list(spliced.mutant_names) == list(rebuilt.mutant_names)
    assert dict(spliced.line_span_by_function_name) == dict(rebuilt.line_span_by_function_name)
    assert dict(spliced.hash_by_function_name) == dict(rebuilt.hash_by_function_name)


@pytest.mark.parametrize("path", CORPUS, ids=[path.name for path in CORPUS])
def test_corpus_files_render_identically(monkeypatch, path):
    spliced, rebuilt = _both_implementations(monkeypatch, str(path), path.read_text())
    assert spliced.mutant_names, "the corpus file should produce mutants"
    _assert_identical(spliced, rebuilt)


@pytest.mark.parametrize("name", sorted(EXTRA_SOURCES), ids=sorted(EXTRA_SOURCES))
def test_blocks_decorators_and_odd_whitespace_render_identically(monkeypatch, name):
    spliced, rebuilt = _both_implementations(monkeypatch, f"{name}.py", EXTRA_SOURCES[name])
    assert spliced.mutant_names
    _assert_identical(spliced, rebuilt)


def test_prerendered_function_emits_its_text_verbatim():
    module = mutmut.mutation.file_mutation.cst.parse_module("")
    node = PrerenderedFunction(name="x_f__mutmut_1", code="    def x_f__mutmut_1(self):\n        return 1\n")

    assert module.code_for_node(node) == node.code
