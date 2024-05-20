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


class MutatorHelper:

    def __init__(self):
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

        self.newline = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}

        self.mutations_by_type = {
            'operator': ("value", OperatorMutation),
            'keyword': ("value", KeywordMutation),
            'number': ("value", NumberMutation),
            'name': ("value", NameMutation),
            'string': ("value", StringMutation),
            'fstring': ("children", FStringMutation),
            'argument': ("children", ArgumentMutation),
            'or_test': ("children", AndOrTestMutation),
            'and_test': ("children", AndOrTestMutation),
            'lambdef': ("children", LambdaMutation),
            'expr_stmt': ("children", ExpressionMutation),
            'decorator': ("children", DecoratorMutation),
            'annassign': ("children", ExpressionMutation),
        }

    def is_a_dunder_whitelist_node(self, node):
        if node.type != 'expr_stmt':
            return False

        if node.children[0].type != 'name':
            return False

        if not node.children[0].value.startswith('__'):
            return False

        if not node.children[0].value.endswith('__'):
            return False

        return node.children[0].value[2:-2] in self.dunder_whitelist

    def is_return_annotation_start(self, node):
        return self.check_node_type_and_value(node, 'operator', '->')

    def is_return_annotation_end(self, node):
        return self.check_node_type_and_value(node, 'operator', ':')

    def get_return_annotation_started(self, node, return_annotation_started):
        if self.is_return_annotation_start(node):
            return_annotation_started = True

        if return_annotation_started and self.is_return_annotation_end(node):
            return_annotation_started = False

        return return_annotation_started

    @staticmethod
    def is_special_node(node):
        return node.type in ('tfpdef', 'import_from', 'import_name')

    @staticmethod
    def is_dynamic_import_node(node):
        return node.type == 'atom_expr' and node.children and node.children[0].type == 'name' and node.children[
            0].value == '__import__'

    @staticmethod
    def should_update_line_index(node, context):
        return node.start_pos[0] - 1 != context.current_line_index

    @staticmethod
    def is_pure_annotation(node):
        return node.type == 'annassign' and len(node.children) == 2

    @staticmethod
    def wrap_or_return_mutation_instance(new, old):
        if isinstance(new, list) and not isinstance(old, list):
            # multiple mutations
            return new

        return [new]

    @staticmethod
    def check_node_type_and_value(node, type, value):
        return node.type == type and node.value == value
