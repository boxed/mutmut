from mutmut.mutator.mutator_iterator import MutatorIterator


class PostOrderIterator(MutatorIterator):
    def __init__(self, root_node, context):
        super().__init__(root_node, context)

    def __next__(self):
        while self._has_next():
            current, visited = self._collections[self._current_position]

            if visited:
                self._collections.pop(self._current_position)
                self._current_position -= 1
                return current

            if self._root != current:
                self._context.stack.append(current)

            return_annotation_started = False

            self._collections[self._current_position] = (current, True)

            if hasattr(current, 'children'):

                for i, child in enumerate(reversed(current.children)):

                    return_annotation_started = self._get_return_annotation_started(child, return_annotation_started)

                    if return_annotation_started:
                        continue

                    if self._is_special_node(child):
                        continue

                    if self._is_dynamic_import_node(child):
                        continue

                    if self._should_update_line_index(child):
                        self._context.current_line_index = child.start_pos[0] - 1
                        self._context.index = 0

                    if self._is_a_dunder_whitelist_node(child):
                        continue


                    self._collections.append((child, False))
                    self._current_position += 1

        raise StopIteration
