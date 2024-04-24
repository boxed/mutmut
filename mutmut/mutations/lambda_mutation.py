from mutation import *
from parso.python.tree import Number, Keyword


class LambdaMutation(Mutation):
    def partition_node_list(self, nodes, value):
        for i, n in enumerate(nodes):
            if hasattr(n, 'value') and n.value == value:
                return nodes[:i], n, nodes[i + 1:]

        assert False, "didn't find node to split on"

    def mutate(self, children, **_):
        pre, op, post = self.partition_node_list(children, value=':')

        if len(post) == 1 and getattr(post[0], 'value', None) == 'None':
            return pre + [op] + [Number(value=' 0', start_pos=post[0].start_pos)]
        else:
            return pre + [op] + [Keyword(value=' None', start_pos=post[0].start_pos)]