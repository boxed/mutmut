# -*- coding: utf-8 -*-
from shutil import move

from parso import parse
from parso.python.tree import Number, Keyword, Name
from tri.declarative import evaluate

from mutmut.patterns import import_from_star_pattern, \
    array_subscript_pattern, function_call_pattern

# We have a global whitelist for constants of the
# pattern __all__, __version__, etc
DUNDER_WHITELIST = [
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

UNTESTED = 'untested'
OK_KILLED = 'ok_killed'
OK_SUSPICIOUS = 'ok_suspicious'
BAD_TIMEOUT = 'bad_timeout'
BAD_SURVIVED = 'bad_survived'


class MutationID(object):
    def __init__(self, line, index, line_number):
        self.line = line
        self.index = index
        self.line_number = line_number

    def __repr__(self):
        return 'MutationID(line="%s", index=%s, line_number=%s)' % (
            self.line, self.index, self.line_number)

    def __eq__(self, other):
        return (self.line, self.index, self.line_number) == \
               (other.line, other.index, other.line_number)


ALL = MutationID(line='%all%', index=-1, line_number=-1)


def number_mutation(value, **_):
    suffix = ''
    if value.upper().endswith('L'):  # pragma: no cover (python 2 specific)
        suffix = value[-1]
        value = value[:-1]

    if value.upper().endswith('J'):
        suffix = value[-1]
        value = value[:-1]

    if value.startswith('0o'):
        base = 8
        value = value[2:]
    elif value.startswith('0x'):
        base = 16
        value = value[2:]
    elif value.startswith('0b'):
        base = 2
        value = value[2:]
    elif value.startswith('0') and len(value) > 1 and value[
        1] != '.':  # pragma: no cover (python 2 specific)
        base = 8
        value = value[1:]
    else:
        base = 10

    try:
        parsed = int(value, base=base)
    except ValueError:
        # Since it wasn't an int, it must be a float
        parsed = float(value)

    result = repr(parsed + 1)
    if not result.endswith(suffix):
        result += suffix
    return result


def string_mutation(value, **_):
    prefix = value[
             :min([x for x in [value.find('"'), value.find("'")] if x != -1])]
    value = value[len(prefix):]

    if value.startswith('"""') or value.startswith("'''"):
        # We assume here that triple-quoted stuff are docs or other things
        # that mutation is meaningless for
        return value
    return prefix + value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]


def lambda_mutation(children, **_):
    pre, op, post = partition_node_list(children, value=':')

    if len(post) == 1 and getattr(post[0], 'value', None) == 'None':
        return pre + [op] + [Number(value=' 0', start_pos=post[0].start_pos)]
    else:
        return pre + [op] + [
            Keyword(value=' None', start_pos=post[0].start_pos)]


def argument_mutation(children, context, **_):
    """
    :type context: Context
    """
    if len(context.stack) >= 3 and context.stack[-3].type in (
            'power', 'atom_expr'):
        stack_pos_of_power_node = -3
    elif len(context.stack) >= 4 and context.stack[-4].type in (
            'power', 'atom_expr'):
        stack_pos_of_power_node = -4
    else:
        return

    power_node = context.stack[stack_pos_of_power_node]

    if power_node.children[0].type == 'name' and power_node.children[
        0].value in context.dict_synonyms:
        c = children[0]
        if c.type == 'name':
            children = children[:]
            children[0] = Name(c.value + 'XX', start_pos=c.start_pos,
                               prefix=c.prefix)
            return children


def keyword_mutation(value, context, **_):
    if len(context.stack) > 2 and \
            context.stack[-2].type == 'comp_op' and value in ('in', 'is'):
        return
    if len(context.stack) > 1 and context.stack[-2].type == 'for_stmt':
        return
    return {
        # 'not': 'not not',
        'not': '',
        'is': 'is not',
        # this will cause "is not not" sometimes,
        # so there's a hack to fix that later
        'in': 'not in',
        'break': 'continue',
        'continue': 'break',
        'True': 'False',
        'False': 'True',
    }.get(value)


def operator_mutation(value, node, **_):
    if import_from_star_pattern.matches(node=node):
        return

    if value in ('**', '*') and node.parent.type == 'param':
        return

    if value == '*' and node.parent.type == 'parameters':
        return

    return {
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

        '+=': '-=',
        '-=': '+=',
        '*=': '/=',
        '/=': '*=',
        '//=': '/=',
        '%=': '/=',
        '<<=': '>>=',
        '>>=': '<<=',
        '&=': '|=',
        '|=': '&=',
        '^=': '&=',
        '**=': '*=',
        '~=': '=',

        '<': '<=',
        '<=': '<',
        '>': '>=',
        '>=': '>',
        '==': '!=',
        '!=': '==',
        '<>': '==',
    }.get(value)


def and_or_test_mutation(children, node, **_):
    children = children[:]
    children[1] = Keyword(
        value={'and': ' or', 'or': ' and'}[children[1].value],
        start_pos=node.start_pos,
    )
    return children


def expression_mutation(children, **_):
    def handle_assignment(children):
        if getattr(children[2], 'value', '---') != 'None':
            x = ' None'
        else:
            x = ' 7'
        children = children[:]
        children[2] = Name(value=x, start_pos=children[2].start_pos)

        return children

    if children[0].type == 'operator' and children[0].value == ':':
        if len(children) > 2 and children[2].value == '=':
            children[1:] = handle_assignment(children[1:])
    elif children[1].type == 'operator' and children[1].value == '=':
        children = handle_assignment(children)

    return children


def decorator_mutation(children, **_):
    assert children[-1].type == 'newline'
    return children[-1:]


def name_mutation(node, value, **_):
    simple_mutants = {
        'True': 'False',
        'False': 'True',
        'deepcopy': 'copy',
        # TODO: This breaks some tests, so should figure out why first: 'None': '0',
        # TODO: probably need to add a lot of things here... some builtins maybe, what more?
    }
    if value in simple_mutants:
        return simple_mutants[value]

    if array_subscript_pattern.matches(node=node):
        return 'None'

    if function_call_pattern.matches(node=node):
        return 'None'


def count_mutations(context):
    """
    :type context: Context
    """
    assert context.mutation_id == ALL
    mutate(context)
    return context.number_of_performed_mutations


def list_mutations(context):
    """
    :type context: Context
    """
    assert context.mutation_id == ALL
    mutate(context)
    return context.performed_mutation_ids


def partition_node_list(nodes, value):
    for i, n in enumerate(nodes):
        if hasattr(n, 'value') and n.value == value:
            return nodes[:i], n, nodes[i + 1:]

    assert False, "didn't find node to split on"


mutations_by_type = {
    'operator': dict(value=operator_mutation),
    'keyword': dict(value=keyword_mutation),
    'number': dict(value=number_mutation),
    'name': dict(value=name_mutation),
    'string': dict(value=string_mutation),
    'argument': dict(children=argument_mutation),
    'or_test': dict(children=and_or_test_mutation),
    'and_test': dict(children=and_or_test_mutation),
    'lambdef': dict(children=lambda_mutation),
    'expr_stmt': dict(children=expression_mutation),
    'decorator': dict(children=decorator_mutation),
    'annassign': dict(children=expression_mutation),
}


class Context(object):
    def __init__(self, source=None, mutation_id=ALL, dict_synonyms=None,
                 filename=None, exclude=lambda context: False, config=None):
        self.index = 0
        self.remove_newline_at_end = False
        if source is not None and source[-1] != '\n':
            source += '\n'
            self.remove_newline_at_end = True
        self.source = source
        self.mutation_id = mutation_id
        self.number_of_performed_mutations = 0
        self.performed_mutation_ids = []
        assert isinstance(mutation_id, MutationID)
        self.current_line_index = 0
        self.filename = filename
        self.exclude = exclude
        self.stack = []
        self.dict_synonyms = (dict_synonyms or []) + ['dict']
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None
        self.config = config

    def exclude_line(self):
        current_line = self.source_by_line_number[self.current_line_index]
        if current_line.startswith('__'):
            word, _, rest = current_line[2:].partition('__')
            if word in DUNDER_WHITELIST and rest.strip()[0] == '=':
                return True

        if current_line.strip() == "__import__('pkg_resources').declare_namespace(__name__)":
            return True

        return self.current_line_index in self.pragma_no_mutate_lines or self.exclude(
            context=self)

    @property
    def source_by_line_number(self):
        if self._source_by_line_number is None:
            self._source_by_line_number = self.source.split('\n')
        return self._source_by_line_number

    @property
    def current_source_line(self):
        return self.source_by_line_number[self.current_line_index]

    @property
    def mutation_id_of_current_index(self):
        return MutationID(line=self.current_source_line, index=self.index,
                          line_number=self.current_line_index)

    @property
    def pragma_no_mutate_lines(self):
        if self._pragma_no_mutate_lines is None:
            self._pragma_no_mutate_lines = {
                i
                for i, line in enumerate(self.source_by_line_number)
                if
                '# pragma:' in line and 'no mutate' in
                line.partition('# pragma:')[-1]
            }
        return self._pragma_no_mutate_lines

    def should_mutate(self):
        if self.mutation_id == ALL:
            return True

        return self.mutation_id in (ALL, self.mutation_id_of_current_index)


def mutate(context):
    """
    :type context: Context
    :return: tuple: mutated source code, number of mutations performed
    """
    try:
        result = parse(context.source, error_recovery=False)
    except Exception:
        print(
            'Failed to parse %s. Internal error from parso follows.' % context.filename)
        print('----------------------------------')
        raise
    mutate_list_of_nodes(result, context=context)
    mutated_source = result.get_code().replace(' not not ', ' ')
    if context.remove_newline_at_end:
        assert mutated_source[-1] == '\n'
        mutated_source = mutated_source[:-1]
    if context.number_of_performed_mutations:
        # If we said we mutated the code, check that it has actually changed
        assert context.source != mutated_source
    context.mutated_source = mutated_source
    return mutated_source, context.number_of_performed_mutations


def mutate_list_of_nodes(result, context):
    """
    :type context: Context
    """
    for i in result.children:
        if i.type == 'operator' and i.value == '->':
            return
        mutate_node(i, context=context)
        # this is just an optimization to stop early
        if context.number_of_performed_mutations and context.mutation_id != ALL:
            return


def mutate_node(node, context):
    """
    :type context: Context
    """
    context.stack.append(node)
    try:

        t = node.type

        if node.type == 'tfpdef':
            return

        if node.start_pos[0] - 1 != context.current_line_index:
            context.current_line_index = node.start_pos[0] - 1
            context.index = 0  # indexes are unique per line, so start over here!

        if hasattr(node, 'children'):
            mutate_list_of_nodes(node, context=context)

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and context.mutation_id != ALL:
                return

        m = mutations_by_type.get(t)

        if m is None:
            return

        for key, value in sorted(m.items()):
            old = getattr(node, key)
            if context.exclude_line():
                continue

            new = evaluate(
                value,
                context=context,
                node=node,
                value=getattr(node, 'value', None),
                children=getattr(node, 'children', None),
            )
            assert not callable(new)
            if new is not None and new != old:
                if context.should_mutate():
                    context.number_of_performed_mutations += 1
                    context.performed_mutation_ids.append(
                        context.mutation_id_of_current_index)
                    setattr(node, key, new)
                context.index += 1

            # this is just an optimization to stop early
            if context.number_of_performed_mutations and context.mutation_id != ALL:
                return
    finally:
        context.stack.pop()


class Mutator:
    def __init__(self,  source=None, filename=None,
                 exclude=lambda context: False):
        """"""
        self.source = source
        if source is None:
            with open(filename) as f:
                self.source = f.read()

        self.filename = filename
        self.exclude = exclude

        self.stack = []
        self.index = 0
        self.current_line_index = 0
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None

        self.context = Context(
           source=self.source,
           filename=self.filename,
           exclude=self.exclude,
        )

    def mutate_list_of_nodes(self, node):
        for child in node.children:
            if child.type == 'operator' and child.value == '->':
                return
            for mutant in self.mutate_node(child):
                yield mutant

    def yield_mutants(self):
        for mutant in self.mutate_list_of_nodes(
                parse(self.source, error_recovery=False)):
                yield mutant

    def mutate_node(self, node):
        self.context.stack.append(node)
        try:
            t = node.type

            if node.type == 'tfpdef':
                return

            if node.start_pos[0] - 1 != self.context.current_line_index:
                self.context.current_line_index = node.start_pos[0] - 1
                self.context.index = 0  # indexes are unique per line, so start over here!

            if hasattr(node, 'children'):
                for mutant in self.mutate_list_of_nodes(node):
                    yield mutant
            m = mutations_by_type.get(t)

            if m is None:
                return

            for key, value in sorted(m.items()):
                old = getattr(node, key)
                if self.context.exclude_line():
                    continue

                new = evaluate(
                    value,
                    context=self.context,
                    node=node,
                    value=getattr(node, 'value', None),
                    children=getattr(node, 'children', None),
                )
                assert not callable(new)
                if new is not None and new != old:
                    if self.context.should_mutate():
                        self.context.number_of_performed_mutations += 1
                        self.context.performed_mutation_ids.append(
                            self.context.mutation_id_of_current_index)
                        setattr(node, key, new)
                        yield Mutant(
                            source_file=self.filename,
                            mutation_id=self.context.mutation_id_of_current_index
                        )
                        setattr(node, key, old)
                    self.context.index += 1
                # this is just an optimization to stop early
                # if self.context.number_of_performed_mutations and self.context.mutation_id != ALL:
                #     return
        finally:
            self.context.stack.pop()



class Mutant:
    """Class representing a Mutant"""

    def __init__(self, source_file, mutation_id, status=UNTESTED):
        """
        :param source_file:
        :type source_file: str
        :param mutation_id:
        :type mutation_id: MutationID
        :param status:
        :type status: str
        """
        self.source_file = source_file
        self.mutation = mutation_id
        self.status = status

    @property
    def _context(self):
        with open(self.source_file) as f:
            source = f.read()
        return Context(
            source=source,
            mutation_id=self.mutation,
            filename=self.source_file
        )

    def apply(self, backup=True):
        """Apply the mutation to the existing source file also create
        a backup"""
        context = self._context
        with open(context.filename) as f:
            code = f.read()
        context.source = code
        if backup:
            with open(context.filename + '.bak', 'w') as f:
                f.write(code)
        result, number_of_mutations_performed = mutate(context)
        if context.number_of_performed_mutations == 0:
            raise ValueError('No mutation performed. '
                             'Are you sure the index is not too big?')
        with open(context.filename, 'w') as f:
            f.write(result)

    def revert(self):
        move(self.source_file + '.bak', self.source_file)
