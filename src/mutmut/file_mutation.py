"""This module contains code for managing mutant creation for whole files."""

from collections import defaultdict
from collections.abc import Iterable, Sequence, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Union
import warnings
import libcst as cst
from libcst.metadata import PositionProvider, MetadataWrapper
import libcst.matchers as m
from mutmut.trampoline_templates import build_trampoline, mangle_function_name, trampoline_impl
from mutmut.node_mutation import mutation_operators, OPERATORS_TYPE

NEVER_MUTATE_FUNCTION_NAMES = { "__getattribute__", "__setattr__", "__new__" }
NEVER_MUTATE_FUNCTION_CALLS = { "len", "isinstance" }

@dataclass
class Mutation:
    original_node: cst.CSTNode
    mutated_node: cst.CSTNode
    contained_by_top_level_function: Union[cst.FunctionDef, None]


def mutate_file_contents(filename: str, code: str, covered_lines: Union[set[int], None] = None) -> tuple[str, Sequence[str]]:
    """Create mutations for `code` and merge them to a single mutated file with trampolines.

    :return: A tuple of (mutated code, list of mutant function names)"""
    module, mutations = create_mutations(code, covered_lines)

    return combine_mutations_to_source(module, mutations)

def create_mutations(
    code: str,
    covered_lines: Union[set[int], None] = None
) -> tuple[cst.Module, list[Mutation]]:
    """Parse the code and create mutations."""
    ignored_lines = pragma_no_mutate_lines(code)

    module = cst.parse_module(code)

    metadata_wrapper = MetadataWrapper(module)
    visitor = MutationVisitor(mutation_operators, ignored_lines, covered_lines)
    module = metadata_wrapper.visit(visitor)

    return module, visitor.mutations

class OuterFunctionProvider(cst.BatchableMetadataProvider):
    """Link all nodes to the top-level function or method that contains them.

    For instance given this module:

    ```
    def foo():
        def bar():
            x = 1
    ```
    
    Then `self.get_metadata(OuterFunctionProvider, <x>)` returns `<foo>`.
    """
    def __init__(self):
        super().__init__()

    def visit_Module(self, node: cst.Module):
        for child in node.body:
            if isinstance(child, cst.FunctionDef):
                # mark all nodes inside the function to belong to this function
                child.visit(OuterFunctionVisitor(self, child))
            elif isinstance(child, cst.ClassDef) and isinstance(child.body, cst.IndentedBlock):
                for method in child.body.body:
                    # mark all nodes inside the class method to belong to this method
                    method.visit(OuterFunctionVisitor(self, method))

        # no need to recurse, we already visited all function and class method children
        return False


class OuterFunctionVisitor(cst.CSTVisitor):
    """Mark all nodes as children of `top_level_node`."""
    def __init__(self, provider: "OuterFunctionProvider", top_level_node: cst.CSTNode) -> None:
        self.provider = provider
        self.top_level_node = top_level_node
        super().__init__()

    def on_visit(self, node: cst.CSTNode):
        self.provider.set_metadata(node, self.top_level_node)
        return True


class MutationVisitor(cst.CSTVisitor):
    """Iterate through all nodes in the module and create mutations for them.
    Ignore nodes at lines `ignore_lines` and several other cases (e.g. nodes within type annotations).
    
    The created mutations will be accessible at `self.mutations`."""

    METADATA_DEPENDENCIES = (PositionProvider, OuterFunctionProvider)

    def __init__(self, operators: OPERATORS_TYPE, ignore_lines: set[int], covered_lines: Union[set[int], None] = None):
        self.mutations: list[Mutation] = []
        self._operators = operators
        self._ignored_lines = ignore_lines
        self._covered_lines = covered_lines

    def on_visit(self, node):
        if self._skip_node_and_children(node):
            return False

        if self._should_mutate_node(node):
            self._create_mutations(node)

        # continue to mutate children
        return True

    def _create_mutations(self, node: cst.CSTNode):
        for t, operator in self._operators:
            if isinstance(node, t):
                for mutated_node in operator(node):
                    mutation = Mutation(
                        original_node=node,
                        mutated_node=mutated_node,
                        contained_by_top_level_function=self.get_metadata(OuterFunctionProvider, node, None), # type: ignore
                    )
                    self.mutations.append(mutation)

    def _should_mutate_node(self, node: cst.CSTNode):
        # currently, the position metadata does not always exist
        # (see https://github.com/Instagram/LibCST/issues/1322)
        position = self.get_metadata(PositionProvider,node, None)
        if position:
            # do not mutate nodes with a pragma: no mutate comment
            if position.start.line in self._ignored_lines:
                return False

            # do not mutate nodes that are not covered
            if self._covered_lines is not None and not position.start.line in self._covered_lines:
                return False

        return True

    def _skip_node_and_children(self, node: cst.CSTNode):
        if (isinstance(node, cst.Call) and isinstance(node.func, cst.Name) and node.func.value in NEVER_MUTATE_FUNCTION_CALLS) \
            or (isinstance(node, cst.FunctionDef) and node.name.value in NEVER_MUTATE_FUNCTION_NAMES):
            return True

        # ignore everything inside of type annotations
        if isinstance(node, cst.Annotation):
            return True

        # default args are executed at definition time 
        # We want to prevent e.g. def foo(x = abs(-1)) mutating to def foo(x = abs(None)),
        # which would raise an Exception as soon as the function is defined (can break the whole import)
        # Therefore we only allow simple default values, where mutations should not raise exceptions
        if isinstance(node, cst.Param) and node.default and not isinstance(node.default, (cst.Name, cst.BaseNumber, cst.BaseString)):
            return True

        # ignore decorated functions, because
        # 1) copying them for the trampoline setup can cause side effects (e.g. multiple @app.post("/foo") definitions)
        # 2) decorators are executed when the function is defined, so we don't want to mutate their arguments and cause exceptions
        # 3) @property decorators break the trampoline signature assignment (which expects it to be a function)
        if isinstance(node, (cst.FunctionDef, cst.ClassDef)) and len(node.decorators):
            return True

        return False



MODULE_STATEMENT = Union[cst.SimpleStatementLine, cst.BaseCompoundStatement]

# convert str trampoline implementations to CST nodes with some whitespace
trampoline_impl_cst = list(cst.parse_module(trampoline_impl).body)
trampoline_impl_cst[-1] = trampoline_impl_cst[-1].with_changes(leading_lines = [cst.EmptyLine(), cst.EmptyLine()])


def combine_mutations_to_source(module: cst.Module, mutations: Sequence[Mutation]) -> tuple[str, Sequence[str]]:
    """Create mutated functions and trampolines for all mutations and compile them to a single source code.
    
    :param module: The original parsed module
    :param mutations: Mutations that should be applied.
    :return: Mutated code and list of mutation names"""

    # copy start of the module (in particular __future__ imports)
    result: list[MODULE_STATEMENT] = get_statements_until_func_or_class(module.body)
    mutation_names: list[str] = []

    # statements we still need to potentially mutate and add to the result
    remaining_statements = module.body[len(result):]

    # trampoline functions
    result.extend(trampoline_impl_cst)

    mutations_within_function = group_by_top_level_node(mutations)

    # We now iterate through all top-level nodes.
    # If they are a function or class method, we mutate and add trampolines.
    # Else we keep the original node without modifications.
    for statement in remaining_statements:
        if isinstance(statement, cst.FunctionDef):
            func = statement
            func_mutants = mutations_within_function.get(func)
            if not func_mutants:
                result.append(func)
                continue
            nodes, mutant_names = function_trampoline_arrangement(func, func_mutants, class_name=None)
            result.extend(nodes)
            mutation_names.extend(mutant_names)
        elif isinstance(statement, cst.ClassDef):
            cls = statement
            if not isinstance(cls.body, cst.IndentedBlock):
                # we don't mutate single-line classes, e.g. `class A: a = 1; b = 2`
                result.append(cls)
            else:
                mutated_body = []
                for method in cls.body.body:
                    method_mutants = mutations_within_function.get(method)
                    if not isinstance(method, cst.FunctionDef) or not method_mutants:
                        mutated_body.append(method)
                        continue
                    nodes, mutant_names = function_trampoline_arrangement(method, method_mutants, class_name=cls.name.value)
                    mutated_body.extend(nodes)
                    mutation_names.extend(mutant_names)

                result.append(cls.with_changes(body=cls.body.with_changes(body=mutated_body)))
        else:
            result.append(statement)

    mutated_module = module.with_changes(body=result)
    return mutated_module.code, mutation_names

def function_trampoline_arrangement(function: cst.FunctionDef, mutants: Iterable[Mutation], class_name: Union[str, None]) -> tuple[Sequence[MODULE_STATEMENT], Sequence[str]]:
    """Create mutated functions and a trampoline that switches between original and mutated versions.
    
    :return: A tuple of (nodes, mutant names)"""
    nodes: list[MODULE_STATEMENT] = []
    mutant_names: list[str] = []

    name = function.name.value
    mangled_name = mangle_function_name(name=name, class_name=class_name) + '__mutmut'

    # copy of original function
    nodes.append(function.with_changes(name=cst.Name(mangled_name + '_orig')))

    # mutated versions of the function
    for i, mutant in enumerate(mutants):
        mutant_name = f'{mangled_name}_{i+1}'
        mutant_names.append(mutant_name)
        mutated_method = function.with_changes(name=cst.Name(mutant_name))
        mutated_method = deep_replace(mutated_method, mutant.original_node, mutant.mutated_node)
        nodes.append(mutated_method) # type: ignore

    # trampoline that forwards the calls
    trampoline = list(cst.parse_module(build_trampoline(orig_name=name, mutants=mutant_names, class_name=class_name)).body)
    trampoline[0] = trampoline[0].with_changes(leading_lines=[cst.EmptyLine()])
    nodes.extend(trampoline)

    return nodes, mutant_names


def get_statements_until_func_or_class(statements: Sequence[MODULE_STATEMENT]) -> list[MODULE_STATEMENT]:
    """Get all statements until we encounter the first function or class definition"""
    result = []

    for stmt in statements:
        if m.matches(stmt, m.FunctionDef() | m.ClassDef()):
            return result
        result.append(stmt)

    return result

def group_by_top_level_node(mutations: Sequence[Mutation]) -> Mapping[cst.CSTNode, Sequence[Mutation]]:
    grouped: dict[cst.CSTNode, list[Mutation]] = defaultdict(list)
    for m in mutations:
        if m.contained_by_top_level_function:
            grouped[m.contained_by_top_level_function].append(m)

    return grouped

def pragma_no_mutate_lines(source: str) -> set[int]:
    return {
        i + 1
        for i, line in enumerate(source.split('\n'))
        if '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[-1]
    }

def deep_replace(tree: cst.CSTNode, old_node: cst.CSTNode, new_node: cst.CSTNode) -> cst.CSTNode:
    """Like the CSTNode.deep_replace method, except that we only replace up to one occurrence of old_node."""
    return tree.visit(ChildReplacementTransformer(old_node, new_node)) # type: ignore

class ChildReplacementTransformer(cst.CSTTransformer):
    def __init__(self, old_node: cst.CSTNode, new_node: cst.CSTNode):
        self.old_node = old_node
        self.new_node = new_node
        self.replaced_node = False

    def on_visit(self, node: cst.CSTNode) -> bool:
        # If the node is one we are about to replace, we shouldn't
        # recurse down it, that would be a waste of time.
        # Also, we stop recursion when we already replaced the node.
        return not (self.replaced_node or node is self.old_node)

    def on_leave(self, original_node: cst.CSTNode, updated_node: cst.CSTNode) -> cst.CSTNode:
        if original_node is self.old_node:
            self.replaced_node = True
            return self.new_node
        return updated_node
