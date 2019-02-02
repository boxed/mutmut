# -*- coding: utf-8 -*-

import re

from parso import parse


class InvalidASTPatternException(Exception):
    pass


class ASTPattern(object):
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
                    assert set(d.keys()) | {'of_type', 'marker_type'} == {
                    'of_type', 'marker_type'}
                    self.markers.append(dict(
                        node=get_leaf(line - 1, column + match.start(),
                                      of_type=d.get('of_type')),
                        marker_type=d.get('marker_type'),
                        name=name,
                    ))

        parse_markers(self.module)

        pattern_nodes = [x['node'] for x in self.markers if
                         x['name'] == 'match' or x['name'] == '']
        if len(pattern_nodes) != 1:
            raise InvalidASTPatternException(
                "Found more than one match node. Match nodes are nodes with "
                "an empty name or with the explicit name 'match'")
        self.pattern = pattern_nodes[0]
        self.marker_type_by_id = {id(x['node']): x['marker_type'] for x in
                                  self.markers}

    def matches(self, node, pattern=None, skip_child=None):
        if pattern is None:
            pattern = self.pattern

        check_value = True
        check_children = True

        # Match type based on the name, so _keyword matches all keywords.
        # Special case for _all that matches everything
        if pattern.type == 'name' and pattern.value.startswith(
                '_') and pattern.value[1:] in ('any', node.type):
            check_value = False

        # The advanced case where we've explicitly marked
        # up a node with the accepted types
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

            for pattern_child, node_child in zip(pattern.children,
                                                 node.children):
                if node_child is skip_child:  # prevent infinite recursion
                    continue

                if not self.matches(node=node_child, pattern=pattern_child,
                                    skip_child=node_child):
                    return False

        # Node value
        if check_value and hasattr(pattern, 'value'):
            if pattern.value != node.value:
                return False

        # Parent
        if pattern.parent.type != 'file_input':  # top level matches nothing
            if skip_child != node:
                return self.matches(node=node.parent, pattern=pattern.parent,
                                    skip_child=node)

        return True


import_from_star_pattern = ASTPattern("""
from _name import *
#                 ^
""")

array_subscript_pattern = ASTPattern("""
_name[_any]
#       ^
""")

function_call_pattern = ASTPattern("""
_name(_any)
#       ^
""")
