# -*- coding: utf-8 -*-
from difflib import unified_diff
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
    mutator = Mutator(context.filename, context.exclude).mutate(context.mutation_id)
    context = mutator.context
    context.number_of_performed_mutations = mutator.context.number_of_performed_mutations
    return context.number_of_performed_mutations


def list_mutations(context):
    """
    :type context: Context
    """
    assert context.mutation_id == ALL
    mutator = Mutator(context.filename, context.exclude).mutate(context.mutation_id)
    context = mutator.context
    context.number_of_performed_mutations = mutator.context.number_of_performed_mutations
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


class Mutator:
    """Mutator that creates native mutmut :class:`Mutants`"""

    def __init__(self, source=None, filename=None, exclude=lambda context: False,
                 mutation_id=ALL, dict_synonyms=None,):
        """"""

        if not source and filename:
            with open(filename) as f:
                self.source = f.read()
        else:
            self.source = source
        if not self.source or self.source[-1] != '\n':
                self.source += '\n'
                self.remove_newline_at_end = True
        else:
            self.remove_newline_at_end = False

        self.filename = filename if filename else "nonesuch"

        self.exclude = exclude
        self.mutation_id = mutation_id
        self.dict_synonyms = (dict_synonyms or []) + ['dict']

        self.stack = []
        self.index = 0
        self.current_line_index = 0
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self.number_of_performed_mutations = 0
        self.performed_mutation_ids = []
        self.current_line_index = 0
        self.filename = filename
        self.exclude = exclude
        self.stack = []
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None

    def mutate_list_of_nodes(self, node):
        for child in node.children:
            if child.type == 'operator' and child.value == '->':
                return
            for mutant in self.mutate_node(child):
                yield mutant
                if self.number_of_performed_mutations and self.mutation_id != ALL:
                    return

    def yield_mutants(self):
        for mutant in self.mutate_list_of_nodes(
                parse(self.source, error_recovery=False)):
                yield mutant

    def mutate_node(self, node):
        self.stack.append(node)
        try:
            t = node.type

            if node.type == 'tfpdef':
                return

            if node.start_pos[0] - 1 != self.current_line_index:
                self.current_line_index = node.start_pos[0] - 1
                self.index = 0  # indexes are unique per line, so start over here!

            if hasattr(node, 'children'):
                # this is just an optimization to stop early
                for mutant in self.mutate_list_of_nodes(node):
                    yield mutant
                if self.number_of_performed_mutations and self.mutation_id != ALL:
                    return

            m = mutations_by_type.get(t)

            if m is None:
                return

            for key, value in sorted(m.items()):
                old = getattr(node, key)
                if self.exclude_line():
                    continue

                new = evaluate(
                    value,
                    context=self,
                    node=node,
                    value=getattr(node, 'value', None),
                    children=getattr(node, 'children', None),
                )
                assert not callable(new)
                if new is not None and new != old:
                    if self.should_mutate():
                        self.number_of_performed_mutations += 1
                        self.performed_mutation_ids.append(
                            self.mutation_id_of_current_index)
                        setattr(node, key, new)
                        yield Mutant(
                            source_filename=self.filename,
                            mutation_id=self.mutation_id_of_current_index
                        )
                        # setattr(node, key, old)
                    self.index += 1
                # this is just an optimization to stop early
                if self.number_of_performed_mutations and self.mutation_id != ALL:
                    return
        finally:
            self.stack.pop()

    def mutate(self):
        result = parse(self.source, error_recovery=False)
        list(self.mutate_list_of_nodes(result))
        # TODO: clean

        mutated_source = result.get_code().replace(' not not ', ' ')
        if self.remove_newline_at_end:
            assert mutated_source[-1] == '\n'
        mutated_source = mutated_source[:-1]
        assert self.source != mutated_source
        return mutated_source

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
                if '# pragma:' in line and 'no mutate' in
                line.partition('# pragma:')[-1]
            }
        return self._pragma_no_mutate_lines

    def should_mutate(self):
        if self.mutation_id == ALL:
            return True

        return self.mutation_id in (ALL, self.mutation_id_of_current_index)


class Mutant:
    """Class representing a Mutant"""

    def __init__(self, source_filename, mutation_id, status=UNTESTED):
        """
        :param source_filename: Filename of the affected source file
        :type source_filename: str
        :param mutation_id:
        :type mutation_id: MutationID
        :param status:
        :type status: str
        """
        self.source_filename = source_filename
        self.mutation_id = mutation_id
        self.status = status

    def apply(self, backup=True):
        """Apply the mutation to the source file"""

        if backup:
            with open(self.source_filename) as f:
                source = f.read()
            with open(self.source_filename + '.bak', 'w') as f:
                f.write(source)
        mutated_source = Mutator(
            filename=self.source_filename,
            mutation_id=self.mutation_id).mutate()
        with open(self.source_filename, 'w') as f:
            f.write(mutated_source)

    def revert(self):
        """Revert the mutation to the source file"""
        move(self.source_filename + '.bak', self.source_filename)

    def get_diff(self):
        """Get the differences between the mutated and
        non-mutated source file"""
        with open(self.source_filename) as f:
            source = f.read()
        mutated_source = Mutator(
            filename=self.source_filename,
            mutation_id=self.mutation_id).mutate()
        output = ""
        for line in unified_diff(
                source.split('\n'),
                mutated_source.split('\n'),
                fromfile=self.source_filename, tofile=self.source_filename,
                lineterm=''):
            output += line + "\n"
        return output
