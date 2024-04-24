from parso.python.tree import FStringStart, FStringEnd

from mutmut.mutations.mutation import Mutation


class FStringMutation(Mutation):
    def __init__(self):
        super().__init__('FStringMutation')

    def mutate(self, children, **kwargs):
        fstring_start: FStringStart = children[0]
        fstring_end: FStringEnd = children[-1]

        children = children[:]  # we need to copy the list here, to not get in place mutation on the next line!

        children[0] = FStringStart(fstring_start.value + 'XX',
                                   start_pos=fstring_start.start_pos,
                                   prefix=fstring_start.prefix)

        children[-1] = FStringEnd('XX' + fstring_end.value,
                                  start_pos=fstring_end.start_pos,
                                  prefix=fstring_end.prefix)

        return children
