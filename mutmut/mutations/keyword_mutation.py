from mutmut.mutations.mutation import Mutation


class KeywordMutation(Mutation):
    def __init__(self):
        super().__init__("KeywordMutation")
        self.keyword_mapping = {
            # 'not': 'not not',
            'not': '',
            'is': 'is not',  # this will cause "is not not" sometimes, so there's a hack to fix that later
            'in': 'not in',
            'break': 'continue',
            'continue': 'break',
            'True': 'False',
            'False': 'True',
        }

    def mutate(self, context, value):
        if len(context.stack) > 2 and context.stack[-2].type in ('comp_op', 'sync_comp_for') and value in ('in', 'is'):
            return

        if len(context.stack) > 1 and context.stack[-2].type == 'for_stmt':
            return

        return self.keyword_mapping.get(value)
