from mutation import *
from parso.python.tree import Keyword


class AndOrTestMutation(Mutation):
    def __init__(self):
        super().__init__('AndOrTestMutation')

    def mutate(self, children, node, **kwargs):
        children = children[:]
        children[1] = Keyword(
            value={'and': ' or', 'or': ' and'}[children[1].value],
            start_pos=node.start_pos,
        )
        return children
