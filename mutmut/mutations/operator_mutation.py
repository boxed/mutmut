from mutmut.helpers.astpattern import ASTPattern
from mutmut.mutations.mutation import Mutation


class OperatorMutation(Mutation):
    def __init__(self):
        super().__init__("OperatorMutation")
        self.import_from_star_pattern = ASTPattern("""
from _name import *
#                 ^
""")
        self.mutation_mapping = {
            '+': '-',
            '-': '+',
            '*': '/',
            '/': '*',
            '//': '/',
            '%': '/',
            '<<': '>>',
            '>>': '<<',
            '&': '|',
            '|': '&',
            '^': '&',
            '**': '*',
            '~': '',

            '+=': ['-=', '='],
            '-=': ['+=', '='],
            '*=': ['/=', '='],
            '/=': ['*=', '='],
            '//=': ['/=', '='],
            '%=': ['/=', '='],
            '<<=': ['>>=', '='],
            '>>=': ['<<=', '='],
            '&=': ['|=', '='],
            '|=': ['&=', '='],
            '^=': ['&=', '='],
            '**=': ['*=', '='],
            '~=': '=',

            '<': '<=',
            '<=': '<',
            '>': '>=',
            '>=': '>',
            '==': '!=',
            '!=': '==',
            '<>': '==',
        }

    def mutate(self, node, value, **kwargs):
        if self.import_from_star_pattern.matches(node=node):
            return

        if value in ('*', '**') and node.parent.type == 'param':
            return

        if value == '*' and node.parent.type == 'parameters':
            return

        if value in ('*', '**') and node.parent.type in ('argument', 'arglist'):
            return

        return self.mutation_mapping.get(value)
