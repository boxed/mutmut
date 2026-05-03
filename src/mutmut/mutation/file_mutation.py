"""This module contains code for managing mutant creation for whole files."""

from collections import defaultdict
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Union
from typing import cast

import libcst as cst
import libcst.matchers as m
from libcst.metadata import MetadataWrapper
from libcst.metadata import PositionProvider

from mutmut.configuration import Config
from mutmut.mutation.mutators import OPERATORS_TYPE
from mutmut.mutation.mutators import mutation_operators
from mutmut.mutation.pragma_handling import IgnoredCode
from mutmut.mutation.pragma_handling import get_ignored_lines
from mutmut.mutation.trampoline_templates import build_mutants_dict_and_name
from mutmut.mutation.trampoline_templates import mangle_function_name
from mutmut.mutation.trampoline_templates import trampoline_imports
from mutmut.type_checking import TypeCheckingError
from mutmut.type_checking import run_type_checker
from mutmut.utils.file_utils import change_cwd
from mutmut.utils.format_utils import get_mutant_name
from mutmut.utils.format_utils import is_mutated_method_name

NEVER_MUTATE_FUNCTION_NAMES = {"__getattribute__", "__setattr__", "__new__"}
NEVER_MUTATE_FUNCTION_CALLS = {"len", "isinstance"}


@dataclass
class Mutation:
    original_node: cst.CSTNode
    mutated_node: cst.CSTNode
    contained_by_top_level_function: cst.FunctionDef | None


def mutate_file_contents(filename: str, code: str, covered_lines: set[int] | None = None) -> tuple[str, Sequence[str]]:
    """Create mutations for `code` and merge them to a single mutated file with trampolines.

    :return: A tuple of (mutated code, list of mutant function names)."""
    module, mutations, ignored_classes, ignored_functions = create_mutations(filename, code, covered_lines)

    mutated_code, mutant_names = combine_mutations_to_source(module, mutations, ignored_classes, ignored_functions)

    # TODO: implement function hashing to skip testing unchanged functions

    return mutated_code, mutant_names


def create_mutations(
    filename: str, code: str, covered_lines: set[int] | None = None
) -> tuple[cst.Module, list[Mutation], set[str], set[str]]:
    """Parse the code and create mutations.

    :param filename: File path forwarded to :class:`PragmaVisitor` for error messages.
    :param code: Python source code to parse and mutate.
    :param covered_lines: If provided, only lines in this set are considered for mutation.
    :return: A tuple of (module, mutations, ignored_classes, ignored_functions)."""
    module = cst.parse_module(code)
    metadata_wrapper = MetadataWrapper(module)

    ignored_code = get_ignored_lines(filename, code, metadata_wrapper)

    visitor = MutationVisitor(
        mutation_operators,
        ignored_code,
        covered_lines,
    )
    module = metadata_wrapper.visit(visitor)

    return module, visitor.mutations, visitor.ignored_classes, visitor.ignored_functions


class OuterFunctionProvider(cst.BatchableMetadataProvider[cst.CSTNode | None]):
    """Link all nodes to the top-level function or method that contains them.

    For instance given this module:

    ```
    def foo():
        def bar():
            x = 1
    ```

    Then `self.get_metadata(OuterFunctionProvider, <x>)` returns `<foo>`."""

    def __init__(self) -> None:
        super().__init__()

    def visit_Module(self, node: cst.Module) -> bool:
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

    def on_visit(self, node: cst.CSTNode) -> bool:
        self.provider.set_metadata(node, self.top_level_node)
        return True


class MutationVisitor(cst.CSTVisitor):
    """Iterate through all nodes in the module and create mutations for them.

    Lines in *ignore_lines* are skipped outright.  Lines in *ignored_node_lines*
    cause the enclosing AST node (and its children) to be skipped, which is used
    for inline ``# pragma: no mutate block`` pragmas.  Several other cases are
    also skipped (e.g. nodes within type annotations).

    The created mutations will be accessible at `self.mutations`."""

    METADATA_DEPENDENCIES = (PositionProvider, OuterFunctionProvider)

    def __init__(
        self,
        operators: OPERATORS_TYPE,
        ignored_code: IgnoredCode,
        covered_lines: set[int] | None = None,
    ):
        self.mutations: list[Mutation] = []
        self._operators = operators
        self._ignored_lines = ignored_code.no_mutate_lines
        self._covered_lines = covered_lines
        self._ignored_node_lines = ignored_code.ignore_node_lines
        self._ignored_pattern_lines = ignored_code.ignore_pattern_lines
        self.ignored_classes: set[str] = set()
        self.ignored_functions: set[str] = set()

    def on_visit(self, node: cst.CSTNode) -> bool:
        if self._skip_node_and_children(node):
            return False

        if self._should_mutate_node(node):
            self._create_mutations(node)

        # continue to mutate children
        return True

    def _create_mutations(self, node: cst.CSTNode) -> None:
        for t, operator in self._operators:
            if isinstance(node, t):
                for mutated_node in operator(node):
                    mutation = Mutation(
                        original_node=node,
                        mutated_node=mutated_node,
                        contained_by_top_level_function=self.get_metadata(OuterFunctionProvider, node, None),  # type: ignore
                    )
                    self.mutations.append(mutation)

    def _should_mutate_node(self, node: cst.CSTNode) -> bool:
        # currently, the position metadata does not always exist
        # (see https://github.com/Instagram/LibCST/issues/1322)
        position = self.get_metadata(PositionProvider, node, None)
        if position:
            # do not mutate nodes with a pragma: no mutate comment
            if position.start.line in self._ignored_lines:
                return False

            if position.start.line in self._ignored_node_lines:
                return False

            # do not mutate nodes that are not covered
            if self._covered_lines is not None and position.start.line not in self._covered_lines:
                return False

        return True

    def _skip_node_and_children(self, node: cst.CSTNode) -> bool:
        position = self.get_metadata(PositionProvider, node, None)
        if position and position.start.line in self._ignored_node_lines:
            if isinstance(node, cst.ClassDef):
                self.ignored_classes.add(node.name.value)
                return True
            elif isinstance(node, cst.FunctionDef):
                self.ignored_functions.add(node.name.value)
                return True
            # other types of nodes (if, elif, for, while, ...) get treated on a line-by-line basis

        if position and position.start.line in self._ignored_pattern_lines:
            if isinstance(node, cst.BaseExpression):
                return True

        if (
            isinstance(node, cst.Call)
            and isinstance(node.func, cst.Name)
            and node.func.value in NEVER_MUTATE_FUNCTION_CALLS
        ) or (isinstance(node, cst.FunctionDef) and node.name.value in NEVER_MUTATE_FUNCTION_NAMES):
            return True

        # ignore everything inside of type annotations
        if isinstance(node, cst.Annotation):
            return True

        # default args are executed at definition time
        # We want to prevent e.g. def foo(x = abs(-1)) mutating to def foo(x = abs(None)),
        # which would raise an Exception as soon as the function is defined (can break the whole import)
        # Therefore we only allow simple default values, where mutations should not raise exceptions
        if (
            isinstance(node, cst.Param)
            and node.default
            and not isinstance(node.default, (cst.Name, cst.BaseNumber, cst.BaseString))
        ):
            return True

        # ignore decorated functions, because
        # 1) copying them for the trampoline setup can cause side effects (e.g. multiple @app.post("/foo") definitions)
        # 2) decorators are executed when the function is defined, so we don't want to mutate their arguments and cause exceptions
        # 3) @property decorators break the trampoline signature assignment (which expects it to be a function)
        # Exception: @staticmethod and @classmethod are allowed because they are predictable and it's easy to set up trampolines for them
        if isinstance(node, cst.FunctionDef) and len(node.decorators):
            if len(node.decorators) == 1:
                decorator = node.decorators[0].decorator
                if isinstance(decorator, cst.Name) and decorator.value in ("staticmethod", "classmethod"):
                    return False
            return True
        if isinstance(node, cst.ClassDef) and len(node.decorators):
            return True

        return False


MODULE_STATEMENT = Union[cst.SimpleStatementLine, cst.BaseCompoundStatement]

# convert str trampoline implementations to CST nodes with some whitespace
trampoline_impl_cst = list(cst.parse_module(trampoline_imports).body)
trampoline_impl_cst[-1] = trampoline_impl_cst[-1].with_changes(leading_lines=[cst.EmptyLine(), cst.EmptyLine()])


def combine_mutations_to_source(
    module: cst.Module,
    mutations: Sequence[Mutation],
    ignored_classes: set[str] | None = None,
    ignored_functions: set[str] | None = None,
) -> tuple[str, Sequence[str]]:
    """Create mutated functions and trampolines for all mutations and compile them to a single source code.

    :param module: The original parsed module.
    :param mutations: Mutations that should be applied.
    :param ignored_classes: Class names to skip transformation for (e.g., enums with pragma: no mutate class).
    :param ignored_functions: Function names to skip transformation for (pragma: no mutate function).
    :return: Mutated code and list of mutation names."""
    ignored_classes = ignored_classes or set()
    ignored_functions = ignored_functions or set()

    # copy start of the module (in particular __future__ imports)
    result: list[MODULE_STATEMENT] = get_statements_until_func_or_class(module.body)
    mutation_names: list[str] = []

    # statements we still need to potentially mutate and add to the result
    remaining_statements = module.body[len(result) :]

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
            empty_dict_nodes, nodes, mutant_dict_assignment_nodes, mutant_names = function_trampoline_arrangement(
                func, func_mutants, class_name=None
            )
            result.extend(empty_dict_nodes)
            result.extend(nodes)
            result.extend(mutant_dict_assignment_nodes)
            mutation_names.extend(mutant_names)
        elif isinstance(statement, cst.ClassDef):
            cls = statement
            if not isinstance(cls.body, cst.IndentedBlock):
                # we don't mutate single-line classes, e.g. `class A: a = 1; b = 2`
                result.append(cls)
            else:
                pre_class_nodes: list[MODULE_STATEMENT] = []
                post_class_nodes: list[MODULE_STATEMENT] = []
                mutated_body = []
                for method in cls.body.body:
                    method_mutants = mutations_within_function.get(method)
                    if not isinstance(method, cst.FunctionDef) or not method_mutants:
                        mutated_body.append(method)
                        continue

                    empty_dict_nodes, nodes, mutant_dict_assignment_nodes, mutant_names = (
                        function_trampoline_arrangement(method, method_mutants, class_name=cls.name.value)
                    )
                    pre_class_nodes.extend(empty_dict_nodes)
                    mutated_body.extend(nodes)
                    post_class_nodes.extend(mutant_dict_assignment_nodes)
                    mutation_names.extend(mutant_names)

                result.extend(pre_class_nodes)
                result.append(cls.with_changes(body=cls.body.with_changes(body=mutated_body)))
                result.extend(post_class_nodes)
        else:
            result.append(statement)

    mutated_module = module.with_changes(body=result)
    return mutated_module.code, mutation_names


def function_trampoline_arrangement(
    function: cst.FunctionDef, mutants: Iterable[Mutation], class_name: str | None
) -> tuple[Sequence[MODULE_STATEMENT], Sequence[MODULE_STATEMENT], Sequence[MODULE_STATEMENT], Sequence[str]]:
    """Create mutated functions and a trampoline that switches between original and mutated versions.

    :return: A tuple of (mutant_dict_declaration_nodes, method_nodes, mutant_dict_assignment_nodes, mutant names)"""
    method_nodes: list[MODULE_STATEMENT] = []
    mutant_names: list[str] = []

    name = function.name.value
    mangled_name = mangle_function_name(name=name, class_name=class_name) + "__mutmut"
    mutants_dict_name = f"mutants_{mangled_name}"

    mutants_dict_empty_code = f"{mutants_dict_name}: MutantDict = {{}}  # type: ignore"
    mutant_dict_declaration_nodes = list(cst.parse_module(mutants_dict_empty_code).body)

    # trampoline with same signature, that forwards the calls to the activated mutant/original method
    # (put first, s.t. it stays next to @overload definitions of this function. mypy needs this)
    decorator_args = [cst.Arg(cst.Name(mutants_dict_name))]
    if len(function.decorators) == 1 and m.matches(function.decorators[0].decorator, m.Name("classmethod")):
        decorator_args.append(cst.Arg(cst.Name("True"), keyword=cst.Name("is_classmethod")))
    trampoline = function.with_changes(
        decorators=[
            *function.decorators,
            cst.Decorator(cst.Call(func=cst.Name("_mutmut_mutated"), args=decorator_args)),
        ]
    )
    method_nodes.append(trampoline)

    # copy of original function
    method_nodes.append(function.with_changes(name=cst.Name(mangled_name + "_orig")))

    # mutated versions of the function
    for i, mutant in enumerate(mutants):
        mutant_name = f"{mangled_name}_{i + 1}"
        mutant_names.append(mutant_name)
        mutated_method = function.with_changes(name=cst.Name(mutant_name))
        mutated_method = cast(cst.FunctionDef, deep_replace(mutated_method, mutant.original_node, mutant.mutated_node))
        method_nodes.append(mutated_method)

    # mapping of mutant to the mutated method
    mutants_dict_code = build_mutants_dict_and_name(
        mangled_name=mangled_name, mutants=mutant_names, mutants_dict_name=mutants_dict_name, class_name=class_name
    )
    mutant_dict_assignment_nodes = list(cst.parse_module(mutants_dict_code).body)
    mutant_dict_assignment_nodes[0] = mutant_dict_assignment_nodes[0].with_changes(leading_lines=[cst.EmptyLine()])

    return mutant_dict_declaration_nodes, method_nodes, mutant_dict_assignment_nodes, mutant_names


def get_statements_until_func_or_class(statements: Sequence[MODULE_STATEMENT]) -> list[MODULE_STATEMENT]:
    """Get all statements until we encounter the first function or class definition"""
    result: list[MODULE_STATEMENT] = []

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


def deep_replace(
    tree: cst.CSTNode, old_node: cst.CSTNode, new_node: cst.CSTNode
) -> cst.CSTNode | cst.RemovalSentinel | cst.FlattenSentinel[cst.CSTNode]:
    """Like the CSTNode.deep_replace method, except that we only replace up to one occurrence of old_node."""
    return tree.visit(ChildReplacementTransformer(old_node, new_node))


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

    def on_leave(self, original_node: cst.CSTNode, updated_node: cst.CSTNode) -> cst.CSTNode:  # type: ignore[override]
        if original_node is self.old_node:
            self.replaced_node = True
            return self.new_node
        return updated_node


@dataclass
class MutatedMethodLocation:
    file: Path
    function_name: str
    line_number_start: int
    line_number_end: int


@dataclass
class FailedTypeCheckMutant:
    method_location: MutatedMethodLocation
    name: str
    error: TypeCheckingError


class MutatedMethodsCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, file: Path):
        self.file = file
        self.found_mutants: list[MutatedMethodLocation] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        name = node.name.value
        if is_mutated_method_name(name):
            range = self.get_metadata(cst.metadata.PositionProvider, node)
            self.found_mutants.append(
                MutatedMethodLocation(
                    file=self.file,
                    function_name=name,
                    line_number_start=range.start.line,
                    line_number_end=range.end.line,
                )
            )

        # do not continue visting children of this function
        # mutated methods are not nested within other methods
        return False


def group_by_path(errors: list[TypeCheckingError]) -> dict[Path, list[TypeCheckingError]]:
    grouped: dict[Path, list[TypeCheckingError]] = defaultdict(list)

    for error in errors:
        grouped[error.file_path].append(error)

    return grouped


def filter_mutants_with_type_checker() -> dict[str, FailedTypeCheckMutant]:
    with change_cwd(Path("mutants")):
        errors = run_type_checker(Config.get().type_check_command)
        errors_by_path = group_by_path(errors)

        mutants_to_skip: dict[str, FailedTypeCheckMutant] = {}

        for path, errors_of_file in errors_by_path.items():
            with open(path, encoding="utf-8") as file:
                source = file.read()
            wrapper = cst.MetadataWrapper(cst.parse_module(source))
            visitor = MutatedMethodsCollector(path)
            wrapper.visit(visitor)
            mutated_methods = visitor.found_mutants

            for error in errors_of_file:
                assert error.file_path == visitor.file
                mutant = next(
                    (m for m in mutated_methods if m.line_number_start <= error.line_number <= m.line_number_end), None
                )
                if mutant is None:
                    raise Exception(
                        f"Could not find mutant for type error {error.file_path}:{error.line_number} ({error.error_description}). \n"
                        "Probably, a code mutation influenced types in unexpected locations. \n"
                        "If your project normally has no type errors and uses mypy/pyrefly, please file an issue with steps to reproduce on github.\n"
                    )

                mutant_name = get_mutant_name(path.relative_to(Path(".").absolute()), mutant.function_name)

                mutants_to_skip[mutant_name] = FailedTypeCheckMutant(
                    method_location=mutant,
                    name=mutant_name,
                    error=error,
                )

        return mutants_to_skip
