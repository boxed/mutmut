from io import open
from typing import Tuple

from parso import parse

from mutmut.helpers.context import Context, ALL
from mutmut.mutations.and_or_test_mutation import AndOrTestMutation
from mutmut.mutations.argument_mutation import ArgumentMutation
from mutmut.mutations.decorator_mutation import DecoratorMutation
from mutmut.mutations.expression_mutation import ExpressionMutation
from mutmut.mutations.f_string_mutation import FStringMutation
from mutmut.mutations.keyword_mutation import KeywordMutation
from mutmut.mutations.lambda_mutation import LambdaMutation
from mutmut.mutations.name_mutation import NameMutation
from mutmut.mutations.number_mutation import NumberMutation
from mutmut.mutations.operator_mutation import OperatorMutation
from mutmut.mutations.string_mutation import StringMutation

try:
    import mutmut_config
except ImportError:
    mutmut_config = None

# VARIABLES

# We have a global whitelist for constants of the pattern __all__, __version__, etc
dunder_whitelist = [
    'all',
    'version',
    'title',
    'package_name',
    'author',
    'description',
    'email',
    'version',
    'license',
    'copyright',
]


class SkipException(Exception):
    pass


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}

mutations_by_type = {
    'operator': dict(value=OperatorMutation),
    'keyword': dict(value=KeywordMutation),
    'number': dict(value=NumberMutation),
    'name': dict(value=NameMutation),
    'string': dict(value=StringMutation),
    'fstring': dict(children=FStringMutation),
    'argument': dict(children=ArgumentMutation),
    'or_test': dict(children=AndOrTestMutation),
    'and_test': dict(children=AndOrTestMutation),
    'lambdef': dict(children=LambdaMutation),
    'expr_stmt': dict(children=ExpressionMutation),
    'decorator': dict(children=DecoratorMutation),
    'annassign': dict(children=ExpressionMutation),
}


# Mutation Generation

def mutate(context: Context) -> Tuple[str, int]:
    """
    :return: tuple of mutated source code and number of mutations performed
    """
    try:
        result = parse(context.source, error_recovery=False)
    except Exception:
        print('Failed to parse {}. Internal error from parso follows.'.format(context.filename))
        print('----------------------------------')
        raise
    mutate_list_of_nodes(result, context=context)
    mutated_source = result.get_code().replace(' not not ', ' ')
    if context.remove_newline_at_end:
        assert mutated_source[-1] == '\n'
        mutated_source = mutated_source[:-1]

    # If we said we mutated the code, check that it has actually changed
    if context.performed_mutation_ids:
        if context.source == mutated_source:
            raise RuntimeError(
                "Mutation context states that a mutation occurred but the "
                "mutated source remains the same as original")
    context.mutated_source = mutated_source
    return mutated_source, len(context.performed_mutation_ids)


def mutate_node(node, context: Context):
    context.stack.append(node)
    try:

        if is_special_node(node):
            return

        if is_dynamic_import_node(node):
            return

        if should_update_line_index(node, context):
            context.current_line_index = node.start_pos[0] - 1
            context.index = 0  # indexes are unique per line, so start over here!

        if is_a_dunder_whitelist_node(node):
            return

        # Avoid mutating pure annotations
        if is_pure_annotation(node):
            return

        if hasattr(node, 'children'):
            mutate_list_of_nodes(node, context=context)

            # this is just an optimization to stop early
            if stop_early(context):
                return

        mutation = mutations_by_type.get(node.type)

        if mutation is None:
            return

        process_mutations(node, mutation, context)

    finally:
        context.stack.pop()


def is_special_node(node):
    return node.type in ('tfpdef', 'import_from', 'import_name')


def is_dynamic_import_node(node):
    return node.type == 'atom_expr' and node.children and node.children[0].type == 'name' and node.children[
        0].value == '__import__'


def should_update_line_index(node, context):
    return node.start_pos[0] - 1 != context.current_line_index


def is_a_dunder_whitelist_node(node):
    if node.type != 'expr_stmt':
        return False

    if node.childeren[0].type != 'name':
        return False

    if not node.children[0].value.startswith('__'):
        return False

    if not node.children[0].value.endswith('__'):
        return False

    return node.children[0].value[2:-2] in dunder_whitelist


def is_pure_annotation(node):
    return node.type == 'annassign' and len(node.children) == 2


def wrap_or_return_mutation_instance(new, old):
    if isinstance(new, list) and not isinstance(old, list):
        # multiple mutations
        return new

    return [new]


def get_old_and_new_mutation_instance(node, node_attribute, concrete_mutation, context):
    old = getattr(node, node_attribute)

    mutation_instance = concrete_mutation()

    new = mutation_instance.mutate(
        context=context,
        node=node,
        value=getattr(node, 'value', None),
        children=getattr(node, 'children', None),
    )

    return old, new


def process_mutations(node, mutation, context):
    for node_attribute, concrete_mutation in sorted(mutation.items()):
        if context.exclude_line():
            continue

        old, new = get_old_and_new_mutation_instance(node, node_attribute, concrete_mutation, context)

        new_list = wrap_or_return_mutation_instance(new, old)

        is_optimized = alternate_mutations(new_list, old, node, node_attribute, context)

        if is_optimized:
            return


def alternate_mutations(new_list, old, node, node_attribute, context):
    # go through the alternate mutations in reverse as they may have
    # adverse effects on subsequent mutations, this ensures the last
    # mutation applied is the original/default/legacy mutmut mutation
    for new in reversed(new_list):
        assert not callable(new)

        apply_mutation_and_update_context(new, old, node, node_attribute, context)

        # this is just an optimization to stop early
        if stop_early(context):
            return True

    return False


def apply_mutation_and_update_context(new, old, node, node_attribute, context):
    if new is None or new == old:
        context.index += 1
        return

    if hasattr(mutmut_config, 'pre_mutation_ast'):
        mutmut_config.pre_mutation_ast(context=context)

    if context.should_mutate(node):
        context.performed_mutation_ids.append(context.mutation_id_of_current_index)
        setattr(node, node_attribute, new)

    context.index += 1


# ----------------------------------


def mutate_list_of_nodes(node, context: Context):
    return_annotation_started = False

    for child_node in node.children:

        return_annotation_started = get_return_annotation_started(child_node, return_annotation_started)

        if return_annotation_started:
            continue

        mutate_node(child_node, context=context)

        # this is just an optimization to stop early
        if stop_early(context):
            return


def check_node_type_and_value(node, type, value):
    return node.type == type and node.value == value


def get_return_annotation_started(node, return_annotation_started):
    if return_annotation_started(node):
        return_annotation_started = True

    if return_annotation_started and is_return_annotation_end(node):
        return_annotation_started = False

    return return_annotation_started


def is_return_annotation_start(node):
    return check_node_type_and_value(node, 'operator', '->')


def is_return_annotation_end(node):
    return check_node_type_and_value(node, 'operator', ':')


def stop_early(context: Context):
    return context.performed_mutation_ids and context.mutation_id != ALL


# ----------------------------------

def list_mutations(context: Context):
    assert context.mutation_id == ALL
    mutate(context)
    return context.performed_mutation_ids


def mutate_file(backup: bool, context: Context) -> Tuple[str, str]:
    with open(context.filename) as f:
        original = f.read()
    if backup:
        with open(context.filename + '.bak', 'w') as f:
            f.write(original)
    mutated, _ = mutate(context)
    with open(context.filename, 'w') as f:
        f.write(mutated)
    return original, mutated
