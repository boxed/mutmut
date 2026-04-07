"""This module contains code for managing mutant creation for whole files."""

from collections import defaultdict
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Union

import libcst as cst
import libcst.matchers as m
from libcst.metadata import MetadataWrapper
from libcst.metadata import PositionProvider

from mutmut.node_mutation import OPERATORS_TYPE
from mutmut.node_mutation import mutation_operators
from mutmut.trampoline_templates import create_trampoline_lookup
from mutmut.trampoline_templates import mangle_function_name
from mutmut.trampoline_templates import trampoline_impl

NEVER_MUTATE_FUNCTION_NAMES = {"__getattribute__", "__setattr__", "__new__"}
NEVER_MUTATE_FUNCTION_CALLS = {"len", "isinstance"}

# Methods that Python treats as implicit classmethods (no @classmethod needed).
# Their first parameter is the class (cls), not an instance (self), and attribute
# lookups must go through the class hierarchy rather than object.__getattribute__.
IMPLICIT_CLASSMETHOD_NAMES = {"__init_subclass__", "__class_getitem__"}


@dataclass
class Mutation:
    original_node: cst.CSTNode
    mutated_node: cst.CSTNode
    contained_by_top_level_function: cst.CSTNode | None


def mutate_file_contents(filename: str, code: str, covered_lines: set[int] | None = None) -> tuple[str, Sequence[str]]:
    """Create mutations for `code` and merge them to a single mutated file with trampolines.

    :return: A tuple of (mutated code, list of mutant function names)"""
    module, mutations = create_mutations(code, covered_lines)

    return combine_mutations_to_source(module, mutations)


def create_mutations(code: str, covered_lines: set[int] | None = None) -> tuple[cst.Module, list[Mutation]]:
    """Parse the code and create mutations."""
    ignored_lines = pragma_no_mutate_lines(code)

    module = cst.parse_module(code)

    metadata_wrapper = MetadataWrapper(module)
    visitor = MutationVisitor(mutation_operators, ignored_lines, covered_lines)
    module = metadata_wrapper.visit(visitor)

    if ignored_lines:
        # Post-filter: for multiline nodes, the start.line check in
        # _should_mutate_node may miss pragmas on inner lines.  Compare
        # the original and mutated source to find the actual changed line
        # and drop the mutation if that line carries a pragma.
        orig_lines = module.code.split("\n")
        filtered: list[Mutation] = []
        for m in visitor.mutations:
            try:
                replaced = module.deep_replace(m.original_node, m.mutated_node)
                new_lines = replaced.code.split("\n")
                changed_line = next(
                    (i + 1 for i, (o, n) in enumerate(zip(orig_lines, new_lines)) if o != n),
                    None,
                )
                if changed_line is not None and changed_line in ignored_lines:
                    continue  # pragma on the mutated line — skip
            except Exception:  # noqa: BLE001
                pass  # keep the mutation if we can't determine the line
            filtered.append(m)
        visitor.mutations = filtered

    return module, visitor.mutations


class OuterFunctionProvider(cst.BatchableMetadataProvider[cst.CSTNode | None]):
    """Link all nodes to the top-level function or method that contains them.

    For instance given this module:

    ```
    def foo():
        def bar():
            x = 1
    ```

    Then `self.get_metadata(OuterFunctionProvider, <x>)` returns `<foo>`.
    """

    def __init__(self) -> None:
        super().__init__()

    def visit_Module(self, node: cst.Module) -> bool | None:
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
    Ignore nodes at lines `ignore_lines` and several other cases (e.g. nodes within type annotations).

    The created mutations will be accessible at `self.mutations`."""

    METADATA_DEPENDENCIES = (PositionProvider, OuterFunctionProvider)

    def __init__(self, operators: OPERATORS_TYPE, ignore_lines: set[int], covered_lines: set[int] | None = None):
        self.mutations: list[Mutation] = []
        self._operators = operators
        self._ignored_lines = ignore_lines
        self._covered_lines = covered_lines

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
                        contained_by_top_level_function=self.get_metadata(OuterFunctionProvider, node, None),
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

            # do not mutate nodes that are not covered
            if self._covered_lines is not None and position.start.line not in self._covered_lines:
                return False

        return True

    def _skip_node_and_children(self, node: cst.CSTNode) -> bool:
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
        if isinstance(node, (cst.FunctionDef, cst.ClassDef)) and len(node.decorators):
            return True

        return False


MODULE_STATEMENT = Union[cst.SimpleStatementLine, cst.BaseCompoundStatement]

# convert str trampoline implementations to CST nodes with some whitespace
trampoline_impl_cst = list(cst.parse_module(trampoline_impl).body)
trampoline_impl_cst[-1] = trampoline_impl_cst[-1].with_changes(leading_lines=[cst.EmptyLine(), cst.EmptyLine()])


def combine_mutations_to_source(module: cst.Module, mutations: Sequence[Mutation]) -> tuple[str, Sequence[str]]:
    """Create mutated functions and trampolines for all mutations and compile them to a single source code.

    :param module: The original parsed module
    :param mutations: Mutations that should be applied.
    :return: Mutated code and list of mutation names"""

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
            else:
                mutated_body = []
                for method in cls.body.body:
                    method_mutants = mutations_within_function.get(method)
                    if not isinstance(method, cst.FunctionDef) or not method_mutants:
                        mutated_body.append(method)
                        continue
                    nodes, mutant_names = function_trampoline_arrangement(
                        method, method_mutants, class_name=cls.name.value
                    )
                    mutated_body.extend(nodes)
                    mutation_names.extend(mutant_names)

                result.append(cls.with_changes(body=cls.body.with_changes(body=mutated_body)))
        else:
            result.append(statement)

    mutated_module = module.with_changes(body=result)
    return mutated_module.code, mutation_names


def _any_param_has_default(function: cst.FunctionDef) -> bool:
    """Return True if any parameter in the function has a default value."""
    for p in function.params.posonly_params:
        if _has_default(p):
            return True
    for p in function.params.params:
        if _has_default(p):
            return True
    for p in function.params.kwonly_params:
        if _has_default(p):
            return True
    return False


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
    orig_name = mangled_name + "_orig"
    nodes.append(function.with_changes(name=cst.Name(orig_name)))

    # When sentinel defaults are used, set __wrapped__ so that inspect.signature()
    # follows it and reports the original (human-readable) signature.
    if _any_param_has_default(function):
        wrapped_stmt = cst.parse_statement(f"{name}.__wrapped__ = {orig_name}\n")
        nodes.append(wrapped_stmt)

    # mutated versions of the function
    for i, mutant in enumerate(mutants):
        mutant_name = f"{mangled_name}_{i + 1}"
        mutant_names.append(mutant_name)
        mutated_method_base = function.with_changes(name=cst.Name(mutant_name))
        mutated_method_result = deep_replace(mutated_method_base, mutant.original_node, mutant.mutated_node)
        nodes.append(mutated_method_result)  # type: ignore[arg-type]

    mutants_dict = list(
        cst.parse_module(create_trampoline_lookup(orig_name=name, mutants=mutant_names, class_name=class_name)).body
    )
    mutants_dict[0] = mutants_dict[0].with_changes(leading_lines=[cst.EmptyLine()])

    nodes.extend(mutants_dict)

    return nodes, mutant_names


def _has_default(param: cst.Param) -> bool:
    """Return True if the parameter has a default value."""
    return param.default is not None and not isinstance(param.default, cst.MaybeSentinel)


def _replace_default_with_sentinel(param: cst.Param) -> cst.Param:
    """Replace the parameter's default value with _MUTMUT_UNSET sentinel."""
    return param.with_changes(default=cst.Name("_MUTMUT_UNSET"))


def _sentinel_if_stmt(param_name: str, target: str) -> cst.If:
    """Create: if <param> is not _MUTMUT_UNSET: <target>['<param>'] = <param>"""
    return cst.If(
        test=cst.Comparison(
            left=cst.Name(param_name),
            comparisons=[cst.ComparisonTarget(cst.IsNot(), cst.Name("_MUTMUT_UNSET"))],
        ),
        body=cst.IndentedBlock([
            cst.SimpleStatementLine([
                cst.Assign(
                    [cst.AssignTarget(cst.Subscript(
                        value=cst.Name(target),
                        slice=[cst.SubscriptElement(cst.Index(cst.SimpleString(f"'{param_name}'")))],
                    ))],
                    cst.Name(param_name),
                ),
            ]),
        ]),
        leading_lines=[],
    )


def create_trampoline_wrapper(function: cst.FunctionDef, mangled_name: str, class_name: str | None) -> cst.FunctionDef:
    is_implicit_classmethod = (
        class_name is not None and function.name.value in IMPLICIT_CLASSMETHOD_NAMES
    )

    # Track which positional params have defaults and need sentinel treatment.
    # We'll move defaulted positional params to kwargs conditionally.
    args: list[cst.Element | cst.StarredElement] = []
    # Params with defaults that need conditional forwarding via kwargs
    sentinel_params: list[str] = []

    for pos_only_param in function.params.posonly_params:
        if _has_default(pos_only_param):
            sentinel_params.append(pos_only_param.name.value)
        else:
            args.append(cst.Element(pos_only_param.name))
    for param in function.params.params:
        if _has_default(param):
            sentinel_params.append(param.name.value)
        else:
            args.append(cst.Element(param.name))
    if isinstance(function.params.star_arg, cst.Param):
        args.append(cst.StarredElement(function.params.star_arg.name))

    # Get the actual first parameter name (usually 'self' or 'cls')
    first_param_name = "self"
    if class_name is not None:
        if function.params.posonly_params:
            first_param_name = function.params.posonly_params[0].name.value
        elif function.params.params:
            first_param_name = function.params.params[0].name.value
        # remove first arg (self/cls — handled by the trampoline function)
        args = args[1:]

    args_assignemnt = cst.Assign([cst.AssignTarget(cst.Name(value="args"))], cst.List(args))

    kwargs: list[cst.DictElement | cst.StarredDictElement] = []
    # Keyword-only params without defaults are always forwarded
    kwonly_sentinel_params: list[str] = []
    for param in function.params.kwonly_params:
        if _has_default(param):
            kwonly_sentinel_params.append(param.name.value)
        else:
            kwargs.append(cst.DictElement(cst.SimpleString(f"'{param.name.value}'"), param.name))
    if isinstance(function.params.star_kwarg, cst.Param):
        kwargs.append(cst.StarredDictElement(function.params.star_kwarg.name))

    kwargs_assignment = cst.Assign([cst.AssignTarget(cst.Name(value="kwargs"))], cst.Dict(kwargs))

    # Build conditional statements for sentinel params
    sentinel_stmts: list[cst.If] = []
    for pname in sentinel_params:
        sentinel_stmts.append(_sentinel_if_stmt(pname, "kwargs"))
    for pname in kwonly_sentinel_params:
        sentinel_stmts.append(_sentinel_if_stmt(pname, "kwargs"))

    # Replace defaults with sentinel in the function signature
    new_posonly_params = [
        _replace_default_with_sentinel(p) if _has_default(p) else p
        for p in function.params.posonly_params
    ]
    new_params = [
        _replace_default_with_sentinel(p) if _has_default(p) else p
        for p in function.params.params
    ]
    new_kwonly_params = [
        _replace_default_with_sentinel(p) if _has_default(p) else p
        for p in function.params.kwonly_params
    ]

    def _get_local_name(func_name: str, *, bind: bool = False) -> cst.BaseExpression:
        # for top level, simply return the name
        if class_name is None:
            return cst.Name(func_name)
        if is_implicit_classmethod:
            # For implicit classmethods (__init_subclass__, __class_getitem__), the first
            # arg is a class, not an instance. object.__getattribute__(cls, ...) would search
            # the metaclass MRO instead of the class hierarchy. Access via ClassName.attr instead.
            attr = cst.Attribute(cst.Name(class_name), cst.Name(func_name))
            if bind:
                # Bind the first parameter so the trampoline can call orig(*args) without
                # prepending cls — matching the bound-method convention of regular methods.
                return cst.Call(
                    func=cst.Attribute(value=attr, attr=cst.Name("__get__")),
                    args=[cst.Arg(cst.Name(first_param_name))],
                )
            return attr
        # for regular methods, use object.__getattribute__(self, name)
        return cst.Call(
            func=cst.Attribute(cst.Name("object"), cst.Name("__getattribute__")),
            args=[cst.Arg(cst.Name(first_param_name)), cst.Arg(cst.SimpleString(f"'{func_name}'"))],
        )

    result: cst.BaseExpression = cst.Call(
        func=cst.Name("_mutmut_trampoline"),
        args=[
            cst.Arg(_get_local_name(f"{mangled_name}_orig", bind=True)),
            cst.Arg(_get_local_name(f"{mangled_name}_mutants")),
            cst.Arg(cst.Name("args")),
            cst.Arg(cst.Name("kwargs")),
            cst.Arg(cst.Name("None" if class_name is None else first_param_name)),
        ],
    )
    # for non-async functions, simply return the value or generator
    result_statement = cst.SimpleStatementLine([cst.Return(result)])

    if function.asynchronous:
        is_generator = _is_generator(function)
        if is_generator:
            # async for i in _mutmut_trampoline(...): yield i
            result_statement = cst.For(  # type: ignore[assignment]
                target=cst.Name("i"),
                iter=result,
                body=cst.IndentedBlock([cst.SimpleStatementLine([cst.Expr(cst.Yield(cst.Name("i")))])]),
                asynchronous=cst.Asynchronous(),
            )
        else:
            # return await _mutmut_trampoline(...)
            result_statement = cst.SimpleStatementLine([cst.Return(cst.Await(result))])

    type_ignore_whitespace = cst.TrailingWhitespace(comment=cst.Comment("# type: ignore"))

    body_stmts: list[cst.BaseStatement] = [
        cst.SimpleStatementLine([args_assignemnt], trailing_whitespace=type_ignore_whitespace),
        cst.SimpleStatementLine([kwargs_assignment], trailing_whitespace=type_ignore_whitespace),
    ]
    body_stmts.extend(sentinel_stmts)
    body_stmts.append(result_statement)

    # Replace defaults with sentinel in the function signature
    new_function_params = function.params.with_changes(
        posonly_params=new_posonly_params,
        params=new_params,
        kwonly_params=new_kwonly_params,
    )

    function.whitespace_after_type_parameters
    return function.with_changes(
        params=new_function_params,
        body=cst.IndentedBlock(body_stmts),
    )


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


def deep_replace(tree: cst.CSTNode, old_node: cst.CSTNode, new_node: cst.CSTNode) -> cst.CSTNode:
    """Like the CSTNode.deep_replace method, except that we only replace up to one occurrence of old_node."""
    return tree.visit(ChildReplacementTransformer(old_node, new_node))  # type: ignore[return-value]


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
    We do so by checking if any child is a Yield statement, but not looking into inner function definitions."""

    def __init__(self, original_function: cst.FunctionDef):
        self.is_generator = False
        self.original_function: cst.FunctionDef = original_function

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        # do not recurse into inner function definitions
        if self.original_function != node:
            return False
        return None

    def visit_Yield(self, node: cst.Yield) -> bool:
        self.is_generator = True
        return False
