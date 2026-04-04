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
from mutmut.mutation.enum_mutation import is_enum_class
from mutmut.mutation.mutators import OPERATORS_TYPE
from mutmut.mutation.mutators import MethodType
from mutmut.mutation.mutators import get_method_type
from mutmut.mutation.mutators import mutation_operators
from mutmut.mutation.pragma_handling import PragmaVisitor
from mutmut.mutation.trampoline_templates import build_enum_trampoline
from mutmut.mutation.trampoline_templates import build_mutants_dict_and_name
from mutmut.mutation.trampoline_templates import mangle_function_name
from mutmut.mutation.trampoline_templates import trampoline_impl
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

    pragma_visitor = PragmaVisitor(filename)
    metadata_wrapper.visit(pragma_visitor)

    visitor = MutationVisitor(
        mutation_operators,
        pragma_visitor.no_mutate_lines,
        covered_lines,
        pragma_visitor.ignore_node_lines,
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
        ignore_lines: set[int],
        covered_lines: set[int] | None = None,
        ignored_node_lines: set[int] | None = None,
    ):
        self.mutations: list[Mutation] = []
        self._operators = operators
        self._ignored_lines = ignore_lines
        self._covered_lines = covered_lines
        self._ignored_node_lines = ignored_node_lines or set()
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
trampoline_impl_cst = list(cst.parse_module(trampoline_impl).body)
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
            nodes, mutant_names = function_trampoline_arrangement(func, func_mutants, class_name=None)
            result.extend(nodes)
            mutation_names.extend(mutant_names)
        elif isinstance(statement, cst.ClassDef):
            cls = statement
            if not isinstance(cls.body, cst.IndentedBlock):
                # we don't mutate single-line classes, e.g. `class A: a = 1; b = 2`
                result.append(cls)
            elif is_enum_class(cls):
                trampoline_nodes, external_nodes, modified_cls, enum_mutant_names = enum_trampoline_arrangement(
                    cls, mutations_within_function
                )
                result.extend(trampoline_nodes)
                result.append(modified_cls)
                result.extend(external_nodes)
                mutation_names.extend(enum_mutant_names)
            else:
                pre_class_nodes: list[MODULE_STATEMENT] = []
                post_class_nodes: list[MODULE_STATEMENT] = []
                mutated_body = []
                for method in cls.body.body:
                    method_mutants = mutations_within_function.get(method)
                    if not isinstance(method, cst.FunctionDef) or not method_mutants:
                        mutated_body.append(method)
                        continue

                    method_type = get_method_type(method)
                    if method_type in (MethodType.STATICMETHOD, MethodType.CLASSMETHOD):
                        trampoline_nodes, ext_nodes, assignment, method_mutant_names = _external_method_injection(
                            method, method_mutants, cls.name.value, method_type
                        )
                        pre_class_nodes.extend(trampoline_nodes)
                        post_class_nodes.extend(ext_nodes)
                        mutated_body.append(assignment)
                        mutation_names.extend(method_mutant_names)
                    else:
                        nodes, mutant_names = function_trampoline_arrangement(
                            method, method_mutants, class_name=cls.name.value
                        )
                        mutated_body.extend(nodes)
                        mutation_names.extend(mutant_names)

                result.extend(pre_class_nodes)
                result.append(cls.with_changes(body=cls.body.with_changes(body=mutated_body)))
                result.extend(post_class_nodes)
        else:
            result.append(statement)

    mutated_module = module.with_changes(body=result)
    return mutated_module.code, mutation_names


def _external_method_injection(
    method: cst.FunctionDef, mutants: Sequence[Mutation], class_name: str, method_type: MethodType
) -> tuple[Sequence[MODULE_STATEMENT], Sequence[MODULE_STATEMENT], cst.SimpleStatementLine, Sequence[str]]:
    """Create external trampoline for a method using external injection pattern.

    This moves mutation code outside the class and uses a simple assignment
    inside the class body. Works for staticmethod, classmethod, and instance methods.

    :param method: The method to create external trampoline for.
    :param mutants: The mutations for this method.
    :param class_name: The containing class name.
    :param method_type: MethodType.STATICMETHOD, MethodType.CLASSMETHOD, or MethodType.INSTANCE.
    :return: A tuple of (trampoline_method_nodes, external_nodes, class_body_assignment, mutant_names)."""
    external_nodes: list[MODULE_STATEMENT] = []
    mutant_names: list[str] = []
    method_name = method.name.value
    prefix = f"_{class_name}_{method_name}"
    mangled_name = mangle_function_name(name=method_name, class_name=class_name) + "__mutmut"

    orig_func = method.with_changes(name=cst.Name(f"{prefix}_orig"), decorators=[])
    external_nodes.append(orig_func)

    for i, mutant in enumerate(mutants):
        mutant_func_name = f"{prefix}_mutant_{i + 1}"
        full_mutant_name = f"{mangled_name}_{i + 1}"
        mutant_names.append(full_mutant_name)

        mutated = method.with_changes(name=cst.Name(mutant_func_name), decorators=[])
        mutated = cast(cst.FunctionDef, deep_replace(mutated, mutant.original_node, mutant.mutated_node))
        external_nodes.append(mutated)
    trampoline_code, mutants_dict_code = build_enum_trampoline(
        class_name=class_name, method_name=method_name, mutant_names=mutant_names, method_type=method_type
    )
    trampoline_nodes = list(cst.parse_module(trampoline_code).body)
    mutants_dict_nodes = list(cst.parse_module(mutants_dict_code).body)
    external_nodes.extend(mutants_dict_nodes)

    if method_type == MethodType.STATICMETHOD:
        assignment_code = f"{method_name} = staticmethod({prefix}_trampoline)"
    elif method_type == MethodType.CLASSMETHOD:
        assignment_code = f"{method_name} = classmethod({prefix}_trampoline)"
    else:
        assignment_code = f"{method_name} = {prefix}_trampoline"

    assignment = cast(cst.SimpleStatementLine, cst.parse_statement(assignment_code))

    return trampoline_nodes, external_nodes, assignment, mutant_names


def function_trampoline_arrangement(
    function: cst.FunctionDef, mutants: Iterable[Mutation], class_name: str | None
) -> tuple[Sequence[MODULE_STATEMENT], Sequence[str]]:
    """Create mutated functions and a trampoline that switches between original and mutated versions.

    :return: A tuple of (nodes, mutant names)"""
    nodes: list[MODULE_STATEMENT] = []
    mutant_names: list[str] = []

    name = function.name.value
    mangled_name = mangle_function_name(name=name, class_name=class_name) + "__mutmut"

    # trampoline with same signature, that forwards the calls to the activated mutant/original method
    # (put first, s.t. it stays next to @overload definitions of this function. mypy needs this)
    nodes.append(create_trampoline_wrapper(function, mangled_name, class_name))

    # copy of original function
    nodes.append(function.with_changes(name=cst.Name(mangled_name + "_orig")))

    # mutated versions of the function
    for i, mutant in enumerate(mutants):
        mutant_name = f"{mangled_name}_{i + 1}"
        mutant_names.append(mutant_name)
        mutated_method = function.with_changes(name=cst.Name(mutant_name))
        mutated_method = cast(cst.FunctionDef, deep_replace(mutated_method, mutant.original_node, mutant.mutated_node))
        nodes.append(mutated_method)

    # mapping of mutant to the mutated method
    mutants_dict_code = build_mutants_dict_and_name(
        orig_name=name,
        class_name=class_name,
        mutants=mutant_names,
    )
    mutants_dict_nodes = list(cst.parse_module(mutants_dict_code).body)
    mutants_dict_nodes[0] = mutants_dict_nodes[0].with_changes(leading_lines=[cst.EmptyLine()])
    nodes.extend(mutants_dict_nodes)

    return nodes, mutant_names


def create_trampoline_wrapper(function: cst.FunctionDef, mangled_name: str, class_name: str | None) -> cst.FunctionDef:
    args: list[cst.Element | cst.StarredElement] = []
    for pos_only_param in function.params.posonly_params:
        args.append(cst.Element(pos_only_param.name))
    for param in function.params.params:
        args.append(cst.Element(param.name))
    if isinstance(function.params.star_arg, cst.Param):
        args.append(cst.StarredElement(function.params.star_arg.name))

    if class_name is not None:
        # remove self arg (handled by the trampoline function)
        args = args[1:]

    args_assignemnt = cst.Assign([cst.AssignTarget(cst.Name(value="args"))], cst.List(args))

    kwargs: list[cst.DictElement | cst.StarredDictElement] = []
    for param in function.params.kwonly_params:
        kwargs.append(cst.DictElement(cst.SimpleString(f"'{param.name.value}'"), param.name))
    if isinstance(function.params.star_kwarg, cst.Param):
        kwargs.append(cst.StarredDictElement(function.params.star_kwarg.name))

    kwargs_assignment = cst.Assign([cst.AssignTarget(cst.Name(value="kwargs"))], cst.Dict(kwargs))

    def _get_local_name(func_name: str) -> cst.BaseExpression:
        # for top level, simply return the name
        if class_name is None:
            return cst.Name(func_name)
        # for class methods, use object.__getattribute__(self, name)
        return cst.Call(
            func=cst.Attribute(cst.Name("object"), cst.Name("__getattribute__")),
            args=[cst.Arg(cst.Name("self")), cst.Arg(cst.SimpleString(f"'{func_name}'"))],
        )

    result: cst.BaseExpression = cst.Call(
        func=cst.Name("_mutmut_trampoline"),
        args=[
            cst.Arg(_get_local_name(f"{mangled_name}_orig")),
            cst.Arg(_get_local_name(f"{mangled_name}_mutants")),
            cst.Arg(cst.Name("args")),
            cst.Arg(cst.Name("kwargs")),
            cst.Arg(cst.Name("None" if class_name is None else "self")),
        ],
    )
    # for non-async functions, simply return the value or generator
    result_statement: cst.BaseStatement = cst.SimpleStatementLine([cst.Return(result)])

    if function.asynchronous:
        is_generator = _is_generator(function)
        if is_generator:
            # async for i in _mutmut_trampoline(...): yield i
            result_statement = cst.For(
                target=cst.Name("i"),
                iter=result,
                body=cst.IndentedBlock([cst.SimpleStatementLine([cst.Expr(cst.Yield(cst.Name("i")))])]),
                asynchronous=cst.Asynchronous(),
            )
        else:
            # return await _mutmut_trampoline(...)
            result_statement = cst.SimpleStatementLine([cst.Return(cst.Await(result))])

    type_ignore_whitespace = cst.TrailingWhitespace(comment=cst.Comment("# type: ignore"))
    return function.with_changes(
        body=cst.IndentedBlock(
            [
                cst.SimpleStatementLine([args_assignemnt], trailing_whitespace=type_ignore_whitespace),
                cst.SimpleStatementLine([kwargs_assignment], trailing_whitespace=type_ignore_whitespace),
                result_statement,
            ],
        ),
    )


def enum_trampoline_arrangement(
    cls: cst.ClassDef, mutations_by_method: Mapping[cst.CSTNode, Sequence[Mutation]]
) -> tuple[Sequence[MODULE_STATEMENT], Sequence[MODULE_STATEMENT], cst.ClassDef, Sequence[str]]:
    """Create external functions and minimal enum class for enum mutation.

    This pattern moves all mutation-related code OUTSIDE the enum class body,
    avoiding the enum metaclass conflict that occurs when class-level attributes
    are added. The enum class only contains simple method assignments.

    :param cls: The enum class definition.
    :param mutations_by_method: Mapping of method nodes to their mutations.
    :return: A tuple of (trampoline_nodes, external_nodes, modified_class, mutant_names)."""
    trampoline_nodes: list[MODULE_STATEMENT] = []
    external_nodes: list[MODULE_STATEMENT] = []
    mutant_names: list[str] = []
    new_body: list[cst.BaseStatement | cst.BaseSmallStatement] = []
    class_name = cls.name.value

    for item in cls.body.body:
        if not isinstance(item, cst.FunctionDef):
            new_body.append(item)
            continue

        method = item
        method_mutants = mutations_by_method.get(method)

        if not method_mutants:
            new_body.append(method)
            continue

        method_type = get_method_type(method)
        if method_type is None:
            new_body.append(method)
            continue

        tramp_nodes, ext_nodes, assignment, method_mutant_names = _external_method_injection(
            method, method_mutants, class_name, method_type
        )
        trampoline_nodes.extend(tramp_nodes)
        external_nodes.extend(ext_nodes)
        new_body.append(assignment)
        mutant_names.extend(method_mutant_names)

    modified_cls = cls.with_changes(body=cls.body.with_changes(body=new_body))

    return trampoline_nodes, external_nodes, modified_cls, mutant_names


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


def pragma_no_mutate_lines(source: str) -> set[int]:
    return {
        i + 1
        for i, line in enumerate(source.split("\n"))
        if "# pragma:" in line and "no mutate" in line.partition("# pragma:")[-1]
    }


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


def _is_generator(function: cst.FunctionDef) -> bool:
    """Return True if the function has yield statement(s)."""
    visitor = IsGeneratorVisitor(function)
    function.visit(visitor)
    return visitor.is_generator


class IsGeneratorVisitor(cst.CSTVisitor):
    """Check if a function is a generator.

    We do so by checking if any child is a Yield statement, but not looking
    into inner function definitions."""

    def __init__(self, original_function: cst.FunctionDef):
        self.is_generator = False
        self.original_function: cst.FunctionDef = original_function

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        if self.original_function != node:
            return False
        return None

    def visit_Yield(self, node: cst.Yield) -> bool:
        self.is_generator = True
        return False


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
                        f"Could not find mutant for type error {error.file_path}:{error.line_number} ({error.error_description}). "
                        "Probably, a code mutation influenced types in unexpected locations. "
                        "If your project normally has no type errors and uses mypy/pyrefly, please file an issue with steps to reproduce on github."
                    )

                mutant_name = get_mutant_name(path.relative_to(Path(".").absolute()), mutant.function_name)

                mutants_to_skip[mutant_name] = FailedTypeCheckMutant(
                    method_location=mutant,
                    name=mutant_name,
                    error=error,
                )

        return mutants_to_skip
