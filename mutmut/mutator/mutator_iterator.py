from abc import abstractmethod
from collections.abc import Iterator


class MutatorIterator(Iterator):

    def __init__(self, root_node, context):
        self._collections = [(root_node, False)] if root_node else []
        self._current_position = 0
        self._context = context

        self.dunder_whitelist = [
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

    def __iter__(self):
        return self

    @abstractmethod
    def __next__(self):
        raise NotImplementedError

    def _has_next(self):
        return len(self._collections) > 0

    @staticmethod
    def _is_special_node(node):
        return node.type in ('tfpdef', 'import_from', 'import_name')

    @staticmethod
    def _is_dynamic_import_node(node):
        return node.type == 'atom_expr' and node.children and node.children[0].type == 'name' and node.children[
            0].value == '__import__'

    def _should_update_line_index(self, node):
        return node.start_pos[0] - 1 != self._context.current_line_index

    def _is_a_dunder_whitelist_node(self, node):
        if node.type != 'expr_stmt':
            return False

        if node.children[0].type != 'name':
            return False

        if not node.children[0].value.startswith('__'):
            return False

        if not node.children[0].value.endswith('__'):
            return False

        return node.children[0].value[2:-2] in self.dunder_whitelist

    @staticmethod
    def _is_pure_annotation(node):
        return node.type == 'annassign' and len(node.children) == 2

    def _get_return_annotation_started(self, node, return_annotation_started):
        if self._is_return_annotation_start(node):
            return_annotation_started = True

        if return_annotation_started and self._is_return_annotation_end(node):
            return_annotation_started = False

        return return_annotation_started

    def _is_return_annotation_start(self, node):
        return self._check_node_type_and_value(node, 'operator', '->')

    def _is_return_annotation_end(self, node):
        return self._check_node_type_and_value(node, 'operator', ':')

    @staticmethod
    def _check_node_type_and_value(node, type, value):
        return node.type == type and node.value == value


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

            return_annotation_started = False

            self._collections[self._current_position] = (current, True)

            if hasattr(current, 'children'):

                for child in reversed(current.children):

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
