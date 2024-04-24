from mutation import *
from parso.python.tree import Name


class ExpressionMutation(Mutation):
    def __init__(self):
        super().__init__('ExpressionMutation')

    def mutate(self, children, **kwargs):
        def handle_assignment(children):
            mutation_index = -1  # we mutate the last value to handle multiple assignement
            if getattr(children[mutation_index], 'value', '---') != 'None':
                x = ' None'
            else:
                x = ' ""'
            children = children[:]
            children[mutation_index] = Name(value=x, start_pos=children[mutation_index].start_pos)

            return children

        if children[0].type == 'operator' and children[0].value == ':':
            if len(children) > 2 and children[2].value == '=':
                children = children[:]  # we need to copy the list here, to not get in place mutation on the next line!
                children[1:] = handle_assignment(children[1:])
        elif children[1].type == 'operator' and children[1].value == '=':
            children = handle_assignment(children)

        return children
