# -*- coding: utf-8 -*-
from __future__ import annotations

import fnmatch
import itertools
import multiprocessing
import os
import re
import shlex
import subprocess
import sys
import toml
from configparser import ConfigParser
from copy import copy as copy_obj
from dataclasses import dataclass, field
from functools import wraps
from io import (
    open,
    TextIOBase,
)
from os.path import isdir
from shutil import (
    move,
    copy,
)
from threading import (
    Timer,
    Thread,
)
from time import time
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

from parso import parse
from parso.python.tree import Name, Number, Keyword, FStringStart, FStringEnd

__version__ = '2.5.1'


if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())
try:
    import mutmut_config
except ImportError:
    mutmut_config = None


@dataclass(frozen=True)
class RelativeMutationID:
    line: str
    index: int
    line_number: int
    filename: Optional[str] = field(default=None, compare=False, hash=False)


ALL = RelativeMutationID(filename='%all%', line='%all%', index=-1, line_number=-1)


class InvalidASTPatternException(Exception):
    pass


class ASTPattern:
    def __init__(self, source, **definitions):
        if definitions is None:
            definitions = {}
        source = source.strip()

        self.definitions = definitions

        self.module = parse(source)

        self.markers = []

        def get_leaf(line, column, of_type=None):
            r = self.module.children[0].get_leaf_for_position((line, column))
            while of_type is not None and r.type != of_type:
                r = r.parent
            return r

        def parse_markers(node):
            if hasattr(node, '_split_prefix'):
                for x in node._split_prefix():
                    parse_markers(x)

            if hasattr(node, 'children'):
                for x in node.children:
                    parse_markers(x)

            if node.type == 'comment':
                line, column = node.start_pos
                for match in re.finditer(r'\^(?P<value>[^\^]*)', node.value):
                    name = match.groupdict()['value'].strip()
                    d = definitions.get(name, {})
                    assert set(d.keys()) | {'of_type', 'marker_type'} == {'of_type', 'marker_type'}
                    self.markers.append(dict(
                        node=get_leaf(line - 1, column + match.start(), of_type=d.get('of_type')),
                        marker_type=d.get('marker_type'),
                        name=name,
                    ))

        parse_markers(self.module)

        pattern_nodes = [x['node'] for x in self.markers if x['name'] == 'match' or x['name'] == '']
        if len(pattern_nodes) != 1:
            raise InvalidASTPatternException("Found more than one match node. Match nodes are nodes with an empty name or with the explicit name 'match'")
        self.pattern = pattern_nodes[0]
        self.marker_type_by_id = {id(x['node']): x['marker_type'] for x in self.markers}

    def matches(self, node, pattern=None, skip_child=None):
        if pattern is None:
            pattern = self.pattern

        check_value = True
        check_children = True

        # Match type based on the name, so _keyword matches all keywords.
        # Special case for _all that matches everything
        if pattern.type == 'name' and pattern.value.startswith('_') and pattern.value[1:] in ('any', node.type):
            check_value = False

        # The advanced case where we've explicitly marked up a node with
        # the accepted types
        elif id(pattern) in self.marker_type_by_id:
            if self.marker_type_by_id[id(pattern)] in (pattern.type, 'any'):
                check_value = False
                check_children = False  # TODO: really? or just do this for 'any'?

        # Check node type strictly
        elif pattern.type != node.type:
            return False

        # Match children
        if check_children and hasattr(pattern, 'children'):
            if len(pattern.children) != len(node.children):
                return False

            for pattern_child, node_child in zip(pattern.children, node.children):
                if node_child is skip_child:  # prevent infinite recursion
                    continue

                if not self.matches(node=node_child, pattern=pattern_child, skip_child=node_child):
                    return False

        # Node value
        if check_value and hasattr(pattern, 'value'):
            if pattern.value != node.value:
                return False

        # Parent
        if pattern.parent.type != 'file_input':  # top level matches nothing
            if skip_child != node:
                return self.matches(node=node.parent, pattern=pattern.parent, skip_child=node)

        return True


# We have a global whitelist for constants of the pattern __all__, __version__, etc

dunder_whitelist = [
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


class SkipException(Exception):
    pass


UNTESTED = 'untested'
OK_KILLED = 'ok_killed'
OK_SUSPICIOUS = 'ok_suspicious'
BAD_TIMEOUT = 'bad_timeout'
BAD_SURVIVED = 'bad_survived'
SKIPPED = 'skipped'


MUTANT_STATUSES = {
    "killed": OK_KILLED,
    "timeout": BAD_TIMEOUT,
    "suspicious": OK_SUSPICIOUS,
    "survived": BAD_SURVIVED,
    "skipped": SKIPPED,
    "untested": UNTESTED,
}


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
    elif value.startswith('0') and len(value) > 1 and value[1] != '.':  # pragma: no cover (python 2 specific)
        base = 8
        value = value[1:]
    else:
        base = 10

    try:
        parsed = int(value, base=base)
        result = repr(parsed + 1)
    except ValueError:
        # Since it wasn't an int, it must be a float
        parsed = float(value)
        # This avoids all very small numbers becoming 1.0, and very
        # large numbers not changing at all
        if (1e-5 < abs(parsed) < 1e5) or (parsed == 0.0):
            result = repr(parsed + 1)
        else:
            result = repr(parsed * 2)

    if not result.endswith(suffix):
        result += suffix
    return result


def string_mutation(value, **_):
    prefix = value[:min(x for x in [value.find('"'), value.find("'")] if x != -1)]
    value = value[len(prefix):]

    if value.startswith('"""') or value.startswith("'''"):
        # We assume here that triple-quoted stuff are docs or other things
        # that mutation is meaningless for
        return prefix + value
    return prefix + value[0] + 'XX' + value[1:-1] + 'XX' + value[-1]


def fstring_mutation(children, **_):
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


def partition_node_list(nodes, value):
    for i, n in enumerate(nodes):
        if hasattr(n, 'value') and n.value == value:
            return nodes[:i], n, nodes[i + 1:]

    assert False, "didn't find node to split on"


def lambda_mutation(children, **_):
    pre, op, post = partition_node_list(children, value=':')

    if len(post) == 1 and getattr(post[0], 'value', None) == 'None':
        return pre + [op] + [Number(value=' 0', start_pos=post[0].start_pos)]
    else:
        return pre + [op] + [Keyword(value=' None', start_pos=post[0].start_pos)]


NEWLINE = {'formatting': [], 'indent': '', 'type': 'endl', 'value': ''}


def argument_mutation(children, context: Context, **_):
    """Mutate the arguments one by one from dict(a=b) to dict(aXXX=b).

    This is similar to the mutation of dict literals in the form {'a': b}.
    """
    if len(context.stack) >= 3 and context.stack[-3].type in ('power', 'atom_expr'):
        stack_pos_of_power_node = -3
    elif len(context.stack) >= 4 and context.stack[-4].type in ('power', 'atom_expr'):
        stack_pos_of_power_node = -4
    else:
        return

    power_node = context.stack[stack_pos_of_power_node]

    if power_node.children[0].type == 'name' and power_node.children[0].value in context.dict_synonyms:
        c = children[0]
        if c.type == 'name':
            children = children[:]
            children[0] = Name(c.value + 'XX', start_pos=c.start_pos, prefix=c.prefix)
            return children


def keyword_mutation(value, context, **_):
    if len(context.stack) > 2 and context.stack[-2].type in ('comp_op', 'sync_comp_for') and value in ('in', 'is'):
        return

    if len(context.stack) > 1 and context.stack[-2].type == 'for_stmt':
        return

    return {
        # 'not': 'not not',
        'not': '',
        'is': 'is not',  # this will cause "is not not" sometimes, so there's a hack to fix that later
        'in': 'not in',
        'break': 'continue',
        'continue': 'break',
        'True': 'False',
        'False': 'True',
    }.get(value)


import_from_star_pattern = ASTPattern("""
from _name import *
#                 ^
""")


def operator_mutation(value, node, **_):
    if import_from_star_pattern.matches(node=node):
        return

    if value in ('*', '**') and node.parent.type == 'param':
        return

    if value == '*' and node.parent.type == 'parameters':
        return

    if value in ('*', '**') and node.parent.type in ('argument', 'arglist'):
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


def decorator_mutation(children, **_):
    assert children[-1].type == 'newline'
    return children[-1:]


array_subscript_pattern = ASTPattern("""
_name[_any]
#       ^
""")


function_call_pattern = ASTPattern("""
_name(_any)
#       ^
""")


def name_mutation(node, value, **_):
    simple_mutants = {
        'True': 'False',
        'False': 'True',
        'deepcopy': 'copy',
        'None': '""',
        # TODO: probably need to add a lot of things here... some builtins maybe, what more?
    }
    if value in simple_mutants:
        return simple_mutants[value]

    if array_subscript_pattern.matches(node=node):
        return 'None'

    if function_call_pattern.matches(node=node):
        return 'None'


mutations_by_type = {
    'operator': dict(value=operator_mutation),
    'keyword': dict(value=keyword_mutation),
    'number': dict(value=number_mutation),
    'name': dict(value=name_mutation),
    'string': dict(value=string_mutation),
    'fstring': dict(children=fstring_mutation),
    'argument': dict(children=argument_mutation),
    'or_test': dict(children=and_or_test_mutation),
    'and_test': dict(children=and_or_test_mutation),
    'lambdef': dict(children=lambda_mutation),
    'expr_stmt': dict(children=expression_mutation),
    'decorator': dict(children=decorator_mutation),
    'annassign': dict(children=expression_mutation),
}

# TODO: detect regexes and mutate them in nasty ways? Maybe mutate all strings as if they are regexes


def should_exclude(context, config: Optional[Config]):
    if config is None or config.covered_lines_by_filename is None:
        return False

    try:
        covered_lines = config.covered_lines_by_filename[context.filename]
    except KeyError:
        if config.coverage_data is not None:
            covered_lines = config.coverage_data.get(os.path.abspath(context.filename))
            config.covered_lines_by_filename[context.filename] = covered_lines
        else:
            covered_lines = None

    if covered_lines is None:
        return True
    current_line = context.current_line_index + 1
    if current_line not in covered_lines:
        return True
    return False


class Context:
    def __init__(
        self,
        source: Optional[str] = None,
        mutation_id=ALL,
        dict_synonyms=None,
        filename=None,
        config: Optional[Config] = None,
        index=0,
    ):
        self.index = index
        self.remove_newline_at_end = False
        self._source = None
        self._set_source(source)
        self.mutation_id = mutation_id
        self.performed_mutation_ids = []
        assert isinstance(mutation_id, RelativeMutationID)
        self.current_line_index = 0
        self.filename = filename
        self.stack = []
        self.dict_synonyms = (dict_synonyms or []) + ['dict']
        self._source_by_line_number = None
        self._pragma_no_mutate_lines = None
        self._path_by_line = None
        self.config = config
        self.skip = False

    def exclude_line(self):
        return self.current_line_index in self.pragma_no_mutate_lines or should_exclude(context=self, config=self.config)

    @property
    def source(self):
        if self._source is None:
            with open(self.filename) as f:
                self._set_source(f.read())
        return self._source

    def _set_source(self, source):
        if source and source[-1] != '\n':
            source += '\n'
            self.remove_newline_at_end = True
        self._source = source

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
        return RelativeMutationID(filename=self.filename, line=self.current_source_line, index=self.index, line_number=self.current_line_index)

    @property
    def pragma_no_mutate_lines(self):
        if self._pragma_no_mutate_lines is None:
            self._pragma_no_mutate_lines = {
                i
                for i, line in enumerate(self.source_by_line_number)
                if '# pragma:' in line and 'no mutate' in line.partition('# pragma:')[-1]
            }
        return self._pragma_no_mutate_lines

    def should_mutate(self, node):
        if self.config and node.type not in self.config.mutation_types_to_apply:
            return False
        if self.mutation_id == ALL:
            return True
        return self.mutation_id in (ALL, self.mutation_id_of_current_index)


def mutate(context: Context) -> Tuple[str, int]:
    """
    :return: tuple of mutated source code and number of mutations performed
    """
    try:
        result = parse(context.source, error_recovery=False)
    except Exception:
        print('Failed to parse {}. Internal error from parso follows.'.format(context.filename))
        print('----------------------------------')
        raise
    mutate_list_of_nodes(result, context=context)
    mutated_source = result.get_code().replace(' not not ', ' ')
    if context.remove_newline_at_end:
        assert mutated_source[-1] == '\n'
        mutated_source = mutated_source[:-1]

    # If we said we mutated the code, check that it has actually changed
    if context.performed_mutation_ids:
        if context.source == mutated_source:
            raise RuntimeError(
                "Mutation context states that a mutation occurred but the "
                "mutated source remains the same as original")
    context.mutated_source = mutated_source
    return mutated_source, len(context.performed_mutation_ids)


def mutate_node(node, context: Context):
    context.stack.append(node)
    try:
        if node.type in ('tfpdef', 'import_from', 'import_name'):
            return

        if node.type == 'atom_expr' and node.children and node.children[0].type == 'name' and node.children[0].value == '__import__':
            return

        if node.start_pos[0] - 1 != context.current_line_index:
            context.current_line_index = node.start_pos[0] - 1
            context.index = 0  # indexes are unique per line, so start over here!

        if node.type == 'expr_stmt':
            if node.children[0].type == 'name' and node.children[0].value.startswith('__') and node.children[0].value.endswith('__'):
                if node.children[0].value[2:-2] in dunder_whitelist:
                    return

        # Avoid mutating pure annotations
        if node.type == 'annassign' and len(node.children) == 2:
            return

        if hasattr(node, 'children'):
            mutate_list_of_nodes(node, context=context)

            # this is just an optimization to stop early
            if context.performed_mutation_ids and context.mutation_id != ALL:
                return

        mutation = mutations_by_type.get(node.type)

        if mutation is None:
            return

        for key, value in sorted(mutation.items()):
            old = getattr(node, key)
            if context.exclude_line():
                continue

            new = value(
                context=context,
                node=node,
                value=getattr(node, 'value', None),
                children=getattr(node, 'children', None),
            )

            if isinstance(new, list) and not isinstance(old, list):
                # multiple mutations
                new_list = new
            else:
                # one mutation
                new_list = [new]

            # go through the alternate mutations in reverse as they may have
            # adverse effects on subsequent mutations, this ensures the last
            # mutation applied is the original/default/legacy mutmut mutation
            for new in reversed(new_list):
                assert not callable(new)
                if new is not None and new != old:
                    if hasattr(mutmut_config, 'pre_mutation_ast'):
                        mutmut_config.pre_mutation_ast(context=context)
                    if context.should_mutate(node):
                        context.performed_mutation_ids.append(context.mutation_id_of_current_index)
                        setattr(node, key, new)
                    context.index += 1
                # this is just an optimization to stop early
                if context.performed_mutation_ids and context.mutation_id != ALL:
                    return
    finally:
        context.stack.pop()


def mutate_list_of_nodes(node, context: Context):
    return_annotation_started = False

    for child_node in node.children:
        if child_node.type == 'operator' and child_node.value == '->':
            return_annotation_started = True

        if return_annotation_started and child_node.type == 'operator' and child_node.value == ':':
            return_annotation_started = False

        if return_annotation_started:
            continue

        mutate_node(child_node, context=context)

        # this is just an optimization to stop early
        if context.performed_mutation_ids and context.mutation_id != ALL:
            return


def list_mutations(context: Context):
    assert context.mutation_id == ALL
    mutate(context)
    return context.performed_mutation_ids


def mutate_file(backup: bool, context: Context) -> Tuple[str, str]:
    with open(context.filename) as f:
        original = f.read()
    if backup:
        with open(context.filename + '.bak', 'w') as f:
            f.write(original)
    mutated, _ = mutate(context)
    with open(context.filename, 'w') as f:
        f.write(mutated)
    return original, mutated


def queue_mutants(
    *,
    progress: Progress,
    config: Config,
    mutants_queue,
    mutations_by_file: Dict[str, List[RelativeMutationID]],
):
    from mutmut.cache import get_cached_mutation_statuses

    try:
        index = 0
        for filename, mutations in mutations_by_file.items():
            cached_mutation_statuses = get_cached_mutation_statuses(filename, mutations, config.hash_of_tests)
            with open(filename) as f:
                source = f.read()
            for mutation_id in mutations:
                cached_status = cached_mutation_statuses.get(mutation_id)
                if cached_status != UNTESTED:
                    progress.register(cached_status)
                    continue
                context = Context(
                    mutation_id=mutation_id,
                    filename=filename,
                    dict_synonyms=config.dict_synonyms,
                    config=copy_obj(config),
                    source=source,
                    index=index,
                )
                mutants_queue.put(('mutant', context))
                index += 1
    finally:
        mutants_queue.put(('end', None))


def check_mutants(mutants_queue, results_queue, cycle_process_after):
    def feedback(line):
        results_queue.put(('progress', line, None, None))

    did_cycle = False

    try:
        count = 0
        while True:
            command, context = mutants_queue.get()
            if command == 'end':
                break

            status = run_mutation(context, feedback)

            results_queue.put(('status', status, context.filename, context.mutation_id))
            count += 1
            if count == cycle_process_after:
                results_queue.put(('cycle', None, None, None))
                did_cycle = True
                break
    finally:
        if not did_cycle:
            results_queue.put(('end', None, None, None))


def run_mutation(context: Context, callback) -> str:
    """
    :return: (computed or cached) status of the tested mutant, one of mutant_statuses
    """
    from mutmut.cache import cached_mutation_status
    cached_status = cached_mutation_status(context.filename, context.mutation_id, context.config.hash_of_tests)

    if cached_status != UNTESTED and context.config.total != 1:
        return cached_status

    config = context.config
    if hasattr(mutmut_config, 'pre_mutation'):
        context.current_line_index = context.mutation_id.line_number
        try:
            mutmut_config.pre_mutation(context=context)
        except SkipException:
            return SKIPPED
        if context.skip:
            return SKIPPED

    if config.pre_mutation:
        result = subprocess.check_output(config.pre_mutation, shell=True).decode().strip()
        if result and not config.swallow_output:
            callback(result)

    try:
        mutate_file(
            backup=True,
            context=context
        )
        start = time()
        try:
            survived = tests_pass(config=config, callback=callback)
            if survived and config.test_command != config._default_test_command and config.rerun_all:
                # rerun the whole test suite to be sure the mutant can not be killed by other tests
                config.test_command = config._default_test_command
                survived = tests_pass(config=config, callback=callback)
        except TimeoutError:
            return BAD_TIMEOUT

        time_elapsed = time() - start
        if not survived and time_elapsed > config.test_time_base + (
            config.baseline_time_elapsed * config.test_time_multiplier
        ):
            return OK_SUSPICIOUS

        if survived:
            return BAD_SURVIVED
        else:
            return OK_KILLED
    except SkipException:
        return SKIPPED

    finally:
        move(context.filename + '.bak', context.filename)
        config.test_command = config._default_test_command  # reset test command to its default in the case it was altered in a hook

        if config.post_mutation:
            result = subprocess.check_output(config.post_mutation, shell=True).decode().strip()
            if result and not config.swallow_output:
                callback(result)


@dataclass
class Config:
    swallow_output: bool
    test_command: str
    _default_test_command: str = field(init=False)
    covered_lines_by_filename: Optional[Dict[str, set[Optional[int]]]]
    baseline_time_elapsed: float
    test_time_multiplier: float
    test_time_base: float
    dict_synonyms: List[str]
    total: int
    using_testmon: bool
    tests_dirs: List[str]
    hash_of_tests: str
    post_mutation: str
    pre_mutation: str
    coverage_data: Dict[str, Dict[int, List[str]]]
    paths_to_mutate: List[str]
    mutation_types_to_apply: Set[str]
    no_progress: bool
    ci: bool
    rerun_all: bool

    def __post_init__(self):
        self._default_test_command = self.test_command


def tests_pass(config: Config, callback) -> bool:
    """
    :return: :obj:`True` if the tests pass, otherwise :obj:`False`
    """
    if config.using_testmon:
        copy('.testmondata-initial', '.testmondata')

    use_special_case = True

    # Special case for hammett! We can do in-process test running which is much faster
    if use_special_case and config.test_command.startswith(hammett_prefix):
        return hammett_tests_pass(config, callback)

    returncode = popen_streaming_output(config.test_command, callback, timeout=config.baseline_time_elapsed * 10)
    return returncode != 1


def config_from_file(**defaults):
    def config_from_pyproject_toml() -> dict:
        try:
            return toml.load('pyproject.toml')['tool']['mutmut']
        except (FileNotFoundError, KeyError):
            return {}

    def config_from_setup_cfg() -> dict:
        config_parser = ConfigParser()
        config_parser.read('setup.cfg')

        try:
            return dict(config_parser['mutmut'])
        except KeyError:
            return {}

    config = config_from_pyproject_toml() or config_from_setup_cfg()

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            for k in list(kwargs.keys()):
                if not kwargs[k]:
                    kwargs[k] = config.get(k, defaults.get(k))
            f(*args, **kwargs)

        return wrapper
    return decorator


def status_printer():
    """Manage the printing and in-place updating of a line of characters

    .. note::
        If the string is longer than a line, then in-place updating may not
        work (it will print a new line at each refresh).
    """
    last_len = [0]

    def p(s):
        s = next(spinner) + ' ' + s
        len_s = len(s)
        output = '\r' + s + (' ' * max(last_len[0] - len_s, 0))
        sys.stdout.write(output)
        sys.stdout.flush()
        last_len[0] = len_s
    return p



def guess_paths_to_mutate() -> str:
    """Guess the path to source code to mutate"""
    this_dir = os.getcwd().split(os.sep)[-1]
    if isdir('lib'):
        return 'lib'
    elif isdir('src'):
        return 'src'
    elif isdir(this_dir):
        return this_dir
    elif isdir(this_dir.replace('-', '_')):
        return this_dir.replace('-', '_')
    elif isdir(this_dir.replace(' ', '_')):
        return this_dir.replace(' ', '_')
    elif isdir(this_dir.replace('-', '')):
        return this_dir.replace('-', '')
    elif isdir(this_dir.replace(' ', '')):
        return this_dir.replace(' ', '')
    raise FileNotFoundError(
        'Could not figure out where the code to mutate is. '
        'Please specify it on the command line using --paths-to-mutate, '
        'or by adding "paths_to_mutate=code_dir" in pyproject.toml or setup.cfg to the [mutmut] '
        'section.')


class Progress:
    def __init__(self, total, output_legend, no_progress=False):
        self.total = total
        self.output_legend = output_legend
        self.progress = 0
        self.skipped = 0
        self.killed_mutants = 0
        self.surviving_mutants = 0
        self.surviving_mutants_timeout = 0
        self.suspicious_mutants = 0
        self.no_progress = no_progress

    def print(self):
        if self.no_progress:
            return
        print_status('{}/{}  {} {}  {} {}  {} {}  {} {}  {} {}'.format(
            self.progress,
            self.total,
            self.output_legend["killed"],
            self.killed_mutants,
            self.output_legend["timeout"],
            self.surviving_mutants_timeout,
            self.output_legend["suspicious"],
            self.suspicious_mutants,
            self.output_legend["survived"],
            self.surviving_mutants,
            self.output_legend["skipped"],
            self.skipped)
        )

    def register(self, status):
        if status == BAD_SURVIVED:
            self.surviving_mutants += 1
        elif status == BAD_TIMEOUT:
            self.surviving_mutants_timeout += 1
        elif status == OK_KILLED:
            self.killed_mutants += 1
        elif status == OK_SUSPICIOUS:
            self.suspicious_mutants += 1
        elif status == SKIPPED:
            self.skipped += 1
        else:
            raise ValueError('Unknown status returned from run_mutation: {}'.format(status))
        self.progress += 1
        self.print()


def check_coverage_data_filepaths(coverage_data):
    for filepath in coverage_data:
        if not os.path.exists(filepath):
            raise ValueError('Filepaths in .coverage not recognized, try recreating the .coverage file manually.')


def get_mutations_by_file_from_cache(mutation_pk):
    from mutmut.cache import filename_and_mutation_id_from_pk
    filename, mutation_id = filename_and_mutation_id_from_pk(int(mutation_pk))
    return {filename: [mutation_id]}


def popen_streaming_output(
    cmd: str, callback: Callable[[str], None], timeout: Optional[float] = None
) -> int:
    """Open a subprocess and stream its output without hard-blocking.

    :param cmd: the command to execute within the subprocess
    :param callback: function that intakes the subprocess' stdout line by line.
        It is called for each line received from the subprocess' stdout stream.
    :param timeout: the timeout time of the subprocess
    :raises TimeoutError: if the subprocess' execution time exceeds
        the timeout time
    :return: the return code of the executed subprocess
    """
    if os.name == 'nt':  # pragma: no cover
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True,
        )
        stdout = process.stdout
    else:
        master, slave = os.openpty()
        process = subprocess.Popen(
            shlex.split(cmd, posix=True),
            stdout=slave,
            stderr=slave
        )
        stdout = os.fdopen(master)
        os.close(slave)

    def kill(process_):
        """Kill the specified process on Timer completion"""
        try:
            process_.kill()
        except OSError:
            pass

    # python 2-3 agnostic process timer
    timer = Timer(timeout, kill, [process])
    timer.daemon = True
    timer.start()

    while process.returncode is None:
        try:
            if os.name == 'nt':  # pragma: no cover
                line = stdout.readline()
                # windows gives readline() raw stdout as a b''
                # need to decode it
                line = line.decode("utf-8")
                if line:  # ignore empty strings and None
                    callback(line)
            else:
                while True:
                    line = stdout.readline()
                    if not line:
                        break
                    callback(line)
        except OSError:
            # This seems to happen on some platforms, including TravisCI.
            # It seems like it's ok to just let this pass here, you just
            # won't get as nice feedback.
            pass
        if not timer.is_alive():
            raise TimeoutError("subprocess running command '{}' timed out after {} seconds".format(cmd, timeout))
        process.poll()

    # we have returned from the subprocess cancel the timer if it is running
    timer.cancel()

    return process.returncode


def hammett_tests_pass(config: Config, callback) -> bool:
    # noinspection PyUnresolvedReferences
    from hammett import main_cli
    modules_before = set(sys.modules.keys())

    # set up timeout
    import _thread
    from threading import (
        Timer,
        current_thread,
        main_thread,
    )

    timed_out = False

    def timeout():
        _thread.interrupt_main()
        nonlocal timed_out
        timed_out = True

    assert current_thread() is main_thread()
    timer = Timer(config.baseline_time_elapsed * 10, timeout)
    timer.daemon = True
    timer.start()

    # Run tests
    try:
        class StdOutRedirect(TextIOBase):
            def write(self, s):
                callback(s)
                return len(s)

        redirect = StdOutRedirect()
        sys.stdout = redirect
        sys.stderr = redirect
        returncode = main_cli(shlex.split(config.test_command[len(hammett_prefix):]))
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        timer.cancel()
    except KeyboardInterrupt:
        timer.cancel()
        if timed_out:
            raise TimeoutError('In process tests timed out')
        raise

    modules_to_force_unload = {x.partition(os.sep)[0].replace('.py', '') for x in config.paths_to_mutate}

    for module_name in sorted(set(sys.modules.keys()) - set(modules_before), reverse=True):
        if any(module_name.startswith(x) for x in modules_to_force_unload) or module_name.startswith('tests') or module_name.startswith('django'):
            del sys.modules[module_name]

    return returncode == 0

CYCLE_PROCESS_AFTER = 100


def run_mutation_tests(
    config: Config,
    progress: Progress,
    mutations_by_file: Dict[str, List[RelativeMutationID]],
):
    from mutmut.cache import update_mutant_status

    # Need to explicitly use the spawn method for python < 3.8 on macOS
    mp_ctx = multiprocessing.get_context('spawn')

    mutants_queue = mp_ctx.Queue(maxsize=100)
    add_to_active_queues(mutants_queue)
    queue_mutants_thread = Thread(
        target=queue_mutants,
        name='queue_mutants',
        daemon=True,
        kwargs=dict(
            progress=progress,
            config=config,
            mutants_queue=mutants_queue,
            mutations_by_file=mutations_by_file,
        )
    )
    queue_mutants_thread.start()

    results_queue = mp_ctx.Queue(maxsize=100)
    add_to_active_queues(results_queue)

    def create_worker():
        t = mp_ctx.Process(
            target=check_mutants,
            name='check_mutants',
            daemon=True,
            kwargs=dict(
                mutants_queue=mutants_queue,
                results_queue=results_queue,
                cycle_process_after=CYCLE_PROCESS_AFTER,
            )
        )
        t.start()
        return t

    t = create_worker()

    while True:
        command, status, filename, mutation_id = results_queue.get()
        if command == 'end':
            t.join()
            break

        elif command == 'cycle':
            t = create_worker()

        elif command == 'progress':
            if not config.swallow_output:
                print(status, end='', flush=True)
            elif not config.no_progress:
                progress.print()

        else:
            assert command == 'status'

            progress.register(status)

            update_mutant_status(file_to_mutate=filename, mutation_id=mutation_id, status=status, tests_hash=config.hash_of_tests)


def read_coverage_data() -> Dict[str, Dict[int, List[str]]]:
    """
    Reads the coverage database and returns a dictionary which maps the filenames to the covered lines and their contexts.
    """
    try:
        # noinspection PyPackageRequirements,PyUnresolvedReferences
        from coverage import Coverage
    except ImportError as e:
        raise ImportError('The --use-coverage feature requires the coverage library. Run "pip install --force-reinstall mutmut[coverage]"') from e
    cov = Coverage('.coverage')
    cov.load()
    data = cov.get_data()
    return {filepath: data.contexts_by_lineno(filepath) for filepath in data.measured_files()}


def read_patch_data(patch_file_path: str):
    try:
        # noinspection PyPackageRequirements
        import whatthepatch
    except ImportError as e:
        raise ImportError('The --use-patch feature requires the whatthepatch library. Run "pip install --force-reinstall mutmut[patch]"') from e
    with open(patch_file_path) as f:
        diffs = whatthepatch.parse_patch(f.read())

    return {
        os.path.normpath(diff.header.new_path): {change.new for change in diff.changes if change.old is None}
        for diff in diffs if diff.changes
    }


def add_mutations_by_file(
    mutations_by_file: Dict[str, List[RelativeMutationID]],
    filename: str,
    dict_synonyms: List[str],
    config: Optional[Config],
):
    with open(filename) as f:
        source = f.read()
    context = Context(
        source=source,
        filename=filename,
        config=config,
        dict_synonyms=dict_synonyms,
    )

    try:
        mutations_by_file[filename] = list_mutations(context)
        from mutmut.cache import register_mutants

        register_mutants(mutations_by_file)
    except Exception as e:
        raise RuntimeError(
            'Failed while creating mutations for {}, for line "{}"'.format(
                context.filename, context.current_source_line
            )
        ) from e


def python_source_files(
    path: str, tests_dirs: List[str], paths_to_exclude: Optional[List[str]] = None
) -> Iterator[str]:
    """Attempt to guess where the python source files to mutate are and yield
    their paths

    :param path: path to a python source file or package directory
    :param tests_dirs: list of directory paths containing test files
        (we do not want to mutate these!)
    :param paths_to_exclude: list of UNIX filename patterns to exclude

    :return: generator listing the paths to the python source files to mutate
    """
    paths_to_exclude = paths_to_exclude or []
    if isdir(path):
        for root, dirs, files in os.walk(path, topdown=True):
            for exclude_pattern in paths_to_exclude:
                dirs[:] = [d for d in dirs if not fnmatch.fnmatch(d, exclude_pattern)]
                files[:] = [f for f in files if not fnmatch.fnmatch(f, exclude_pattern)]

            dirs[:] = [d for d in dirs if os.path.join(root, d) not in tests_dirs]
            for filename in files:
                if filename.endswith('.py'):
                    yield os.path.join(root, filename)
    else:
        yield path


def compute_exit_code(
    progress: Progress, exception: Optional[Exception] = None, ci: bool = False
) -> int:
    """Compute an exit code for mutmut mutation testing

    The following exit codes are available for mutmut (as documented for the CLI run command):
     * 0 if all mutants were killed (OK_KILLED)
     * 1 if a fatal error occurred
     * 2 if one or more mutants survived (BAD_SURVIVED)
     * 4 if one or more mutants timed out (BAD_TIMEOUT)
     * 8 if one or more mutants caused tests to take twice as long (OK_SUSPICIOUS)

     Exit codes 1 to 8 will be bit-ORed so that it is possible to know what
     different mutant statuses occurred during mutation testing.

     When running with ci=True (--CI flag enabled), the exit code will always be
     1 for a fatal error or 0 for any other case.

    :param exception:
    :param progress:
    :param ci:

    :return: integer noting the exit code of the mutation tests.
    """
    code = 0
    if exception is not None:
        code = code | 1
    if ci:
        return code
    if progress.surviving_mutants > 0:
        code = code | 2
    if progress.surviving_mutants_timeout > 0:
        code = code | 4
    if progress.suspicious_mutants > 0:
        code = code | 8
    return code


hammett_prefix = 'python -m hammett '
spinner = itertools.cycle('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')
print_status = status_printer()

# List of active multiprocessing queues
_active_queues = []


def add_to_active_queues(queue):
    _active_queues.append(queue)


def close_active_queues():
    for queue in _active_queues:
        queue.close()
