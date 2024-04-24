from mutmut.mutations.mutation import Mutation


class DecoratorMutation(Mutation):

    def __init__(self):
        super().__init__('DecoratorMutation')

    def mutate(self, children, **kwargs):
        assert children[-1].type == 'newline'
        return children[-1:]
