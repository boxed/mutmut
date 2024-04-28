from io import open
from typing import Tuple

from parso import parse
from parso.python.tree import Name, Number, Keyword, FStringStart, FStringEnd

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

CYCLE_PROCESS_AFTER = 100

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
        if node.type in ('tfpdef', 'import_from', 'import_name'):
            return

        if node.type == 'atom_expr' and node.children and node.children[0].type == 'name' and node.children[
            0].value == '__import__':
            return

        if node.start_pos[0] - 1 != context.current_line_index:
            context.current_line_index = node.start_pos[0] - 1
            context.index = 0  # indexes are unique per line, so start over here!

        if node.type == 'expr_stmt':
            if (node.children[0].type == 'name' and node.children[0].value.startswith('__') and
                    node.children[0].value.endswith('__')):
                if node.children[0].value[2:-2] in dunder_whitelist:
                    return

        # Avoid mutating pure annotations
        if node.type == 'annassign' and len(node.children) == 2:
            return

        if hasattr(node, 'children'):
            mutate_list_of_nodes(node, context=context)

            # this is just an optimization to stop early
            if context.performed_mutation_ids and context.mutation_id != ALL:
                return

        mutation = mutations_by_type.get(node.type)

        if mutation is None:
            return

        for node_attribute, concrete_mutation in sorted(mutation.items()):
            old = getattr(node, node_attribute)
            if context.exclude_line():
                continue

            mutation_instance = concrete_mutation()
            new = mutation_instance.mutate(
                context=context,
                node=node,
                value=getattr(node, 'value', None),
                children=getattr(node, 'children', None),
            )

            if isinstance(new, list) and not isinstance(old, list):
                # multiple mutations
                new_list = new
            else:
                # one mutation
                new_list = [new]

            # go through the alternate mutations in reverse as they may have
            # adverse effects on subsequent mutations, this ensures the last
            # mutation applied is the original/default/legacy mutmut mutation
            for new in reversed(new_list):
                assert not callable(new)
                if new is not None and new != old:
                    if hasattr(mutmut_config, 'pre_mutation_ast'):
                        mutmut_config.pre_mutation_ast(context=context)
                    if context.should_mutate(node):
                        context.performed_mutation_ids.append(context.mutation_id_of_current_index)
                        setattr(node, node_attribute, new)
                    context.index += 1
                # this is just an optimization to stop early
                if context.performed_mutation_ids and context.mutation_id != ALL:
                    return
    finally:
        context.stack.pop()


def mutate_list_of_nodes(node, context: Context):
    return_annotation_started = False

    for child_node in node.children:
        if child_node.type == 'operator' and child_node.value == '->':
            return_annotation_started = True

        if return_annotation_started and child_node.type == 'operator' and child_node.value == ':':
            return_annotation_started = False

        if return_annotation_started:
            continue

        mutate_node(child_node, context=context)

        # this is just an optimization to stop early
        if context.performed_mutation_ids and context.mutation_id != ALL:
            return


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
