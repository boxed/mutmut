from mutmut.helpers.astpattern import ASTPattern
from mutmut.mutations.mutation import Mutation


class NameMutation(Mutation):
    def __init__(self):
        super().__init__("NameMutation")
        self.array_subscript_pattern = ASTPattern("""
_name[_any]
#       ^
""")
        self.function_call_pattern = ASTPattern("""
_name(_any)
#       ^
""")
        self.simple_mutants = {
            'True': 'False',
            'False': 'True',
            'deepcopy': 'copy',
            'None': '""',
        }

    def mutate(self, node, value):
        if value in self.simple_mutants:
            return self.simple_mutants[value]

        if self.array_subscript_pattern.matches(node=node):
            return 'None'

        if self.function_call_pattern.matches(node=node):
            return 'None'