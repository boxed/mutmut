import multiprocessing
import os.path
from io import open
from typing import Tuple

from parso import parse

from mutmut.helpers.context import Context, ALL
from mutmut.mutator.mutator_iterator import PostOrderIterator

try:
    import mutmut_config
except ImportError:
    mutmut_config = None

from mutmut.mutator.mutator_helper import MutatorHelper


class SkipException(Exception):
    pass


class Mutator:

    def __init__(self, context: Context):
        self.context = context
        self.helper = MutatorHelper()

    def mutate(self) -> Tuple[str, int]:
        """
        :return: tuple of mutated source code and number of mutations performed
        """
        try:
            result = parse(self.context.source, error_recovery=False)
        except Exception:
            print('Failed to parse {}. Internal error from parso follows.'.format(self.context.filename))
            print('----------------------------------')
            raise

        for node in PostOrderIterator(result, self.context):
            self.mmutate(node)

        mutated_source = result.get_code().replace(' not not ', ' ')
        if self.context.remove_newline_at_end:
            assert mutated_source[-1] == '\n'
            mutated_source = mutated_source[:-1]

        # If we said we mutated the code, check that it has actually changed
        if self.context.performed_mutation_ids:
            if self.context.source == mutated_source:
                raise RuntimeError(
                    "Mutation context states that a mutation occurred but the "
                    "mutated source remains the same as original")
        self.context.mutated_source = mutated_source
        return mutated_source, len(self.context.performed_mutation_ids)

    def mutate_node(self, node):
        mutation = self.helper.mutations_by_type.get(node.type)

        if mutation is None:
            return

        self.process_mutations(node, mutation)

    def get_old_and_new_mutation_instance(self, node, node_attribute, concrete_mutation):
        old = getattr(node, node_attribute)

        mutation_instance = concrete_mutation()

        new = mutation_instance.mutate(
            context=self.context,
            node=node,
            value=getattr(node, 'value', None),
            children=getattr(node, 'children', None),
        )

        return old, new

    def process_mutations(self, node, mutation):
        node_attribute, concrete_mutation = mutation

        if self.context.exclude_line():
            return

        old, new = self.get_old_and_new_mutation_instance(node, node_attribute, concrete_mutation)

        new_list = self.helper.wrap_or_return_mutation_instance(new, old)

        # TODO: look into why and if we need this
        is_optimized = self.alternate_mutations(new_list, old, node, node_attribute)

        if is_optimized:
            return

    def alternate_mutations(self, new_list, old, node, node_attribute):
        # go through the alternate mutations in reverse as they may have
        # adverse effects on subsequent mutations, this ensures the last
        # mutation applied is the original/default/legacy mutmut mutation
        for new in reversed(new_list):
            assert not callable(new)

            self.apply_mutation_and_update_context(new, old, node, node_attribute)

            # this is just an optimization to stop early
            if self.stop_early():
                return True

        return False

    def apply_mutation_and_update_context(self, new, old, node, node_attribute):
        if new is None or new == old:
            return

        if hasattr(mutmut_config, 'pre_mutation_ast'):
            mutmut_config.pre_mutation_ast(context=self.context)

        if self.context.should_mutate(node):
            self.context.performed_mutation_ids.append(self.context.mutation_id_of_current_index)
            setattr(node, node_attribute, new)

        self.context.index += 1

    def stop_early(self):
        return self.context.performed_mutation_ids and self.context.mutation_id != ALL

    def list_mutations(self):
        assert self.context.mutation_id == ALL
        self.mutate()
        return self.context.performed_mutation_ids

    def mutate_file(self, backup: bool, test_lock: multiprocessing.Lock) -> Tuple[str, str]:
        original = (f'{self.context.filename}.bak' if os.path.isfile(f'{self.context.filename}.bak')
                    else self.context.filename)
        with open(original) as f:
            original_content = f.read()
        if backup and not os.path.isfile(f'{self.context.filename}.bak'):
            with open(f'{self.context.filename}.bak', 'w') as f:
                f.write(original_content)
        mutated, _ = self.mutate()
        test_lock.acquire()
        with open(f'{self.context.filename}', 'w') as f:
            f.write(mutated)
        return original_content, mutated
