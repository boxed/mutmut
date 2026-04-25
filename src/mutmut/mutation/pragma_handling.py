"""Pragma comment parsing for mutation control via LibCST."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

import libcst as cst
from libcst.metadata import PositionProvider

from mutmut.configuration import Config


@dataclass
class IgnoredCode:
    """1-indexed line numbers"""

    no_mutate_lines: set[int]
    ignore_node_lines: set[int]
    ignore_pattern_lines: set[int]


def get_ignored_lines(filename: str, source: str, metadata_wrapper: cst.MetadataWrapper) -> IgnoredCode:
    pragma_visitor = PragmaVisitor(filename)
    metadata_wrapper.visit(pragma_visitor)

    lines_ignored_by_pattern = get_lines_ignored_by_pattern(source)

    return IgnoredCode(
        no_mutate_lines=pragma_visitor.no_mutate_lines,
        ignore_node_lines=pragma_visitor.ignore_node_lines,
        ignore_pattern_lines=lines_ignored_by_pattern,
    )


def get_lines_ignored_by_pattern(source: str) -> set[int]:
    matching_lines = set()
    for pattern in Config.get().do_not_mutate_patterns:
        compiled_pattern = re.compile(pattern)
        for i, line in enumerate(source.splitlines()):
            if compiled_pattern.search(line):
                matching_lines.add(i + 1)

    return matching_lines


class PragmaParseError(Exception):
    pass


def _parse_pragma_token(comment: cst.Comment | None) -> str | None:
    """Return 'block', 'start', 'end', 'bare', or None."""
    if comment is None:
        return None
    text = comment.value
    if "# pragma:" not in text or "no mutate" not in text:
        return None
    tail = text.partition("no mutate")[-1].strip()
    tokens = tail.lstrip(": ").split(",", 1)[0].split()
    tok = tokens[0] if tokens else None
    if tok in ("block", "start", "end"):
        return tok
    return "bare"


class PragmaVisitor(cst.CSTVisitor):
    """Walk a LibCST tree to collect pragma-suppressed line numbers.

    After visiting, ``no_mutate_lines`` contains lines where individual
    mutations should be suppressed, and ``ignore_node_lines`` contains
    lines where entire AST nodes (and their children) should be skipped."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, filename: str):
        self.filename = filename
        self.no_mutate_lines: set[int] = set()
        self.ignore_node_lines: set[int] = set()
        self._context_type: str | None = None
        self._context_start_line: int | None = None

    def _open_context(self, kind: str, line_num: int) -> None:
        if self._context_type is not None:
            raise PragmaParseError(
                f"Cannot open no mutate context at {self.filename}:{line_num}\n"
                f"\tPragma context already opened at {self.filename}:{self._context_start_line}"
            )
        self._context_type = kind
        self._context_start_line = line_num

    def _close_context(self) -> None:
        self._context_type = None
        self._context_start_line = None

    def _scan_empty_lines(self, lines: Sequence[cst.EmptyLine]) -> list[tuple[str, int]]:
        """Scan EmptyLine nodes for pragma comments.

        :param lines: The lines to scan for pragma comments.
        :return: (token, line_number) pairs so callers like ``_scan_body_stmts``
            can react to ``block`` tokens by marking sibling ranges."""
        results: list[tuple[str, int]] = []
        for line in lines:
            if line.comment is None:
                continue
            tok = _parse_pragma_token(line.comment)
            if tok is None:
                continue
            line_num = self.get_metadata(PositionProvider, line).start.line
            if tok == "block":
                self._open_context("block", line_num)
                self.no_mutate_lines.add(line_num)
            elif tok == "start":
                self._open_context("selection", line_num)
                self.no_mutate_lines.add(line_num)
            elif tok == "end":
                if self._context_type != "selection":
                    raise PragmaParseError(
                        f"# pragma: no mutate end at {self.filename}:{line_num} without a # pragma: no mutate start"
                        + (
                            f"\n\tCurrent no mutate context started at {self.filename}:{self._context_start_line}"
                            if self._context_type is not None
                            else ""
                        )
                    )
                if self._context_start_line is None:
                    raise ValueError("Context start line cannot be None")
                self.no_mutate_lines.update(range(self._context_start_line, line_num + 1))
                self._close_context()
            else:
                self.no_mutate_lines.add(line_num)
            results.append((tok, line_num))
        return results

    def _scan_body_stmts(
        self,
        body: Sequence[cst.BaseStatement | cst.BaseCompoundStatement | cst.SimpleStatementLine],
    ) -> None:
        """Scan ``leading_lines`` of each statement for standalone pragmas.

        Shared by ``visit_Module`` (module-level body) and
        ``visit_IndentedBlock`` (block-level body)."""
        block_from_idx: int | None = None
        for i, stmt in enumerate(body):
            found = self._scan_empty_lines(getattr(stmt, "leading_lines", []))
            for tok, _ in found:
                if tok == "block" and block_from_idx is None:
                    block_from_idx = i
        if block_from_idx is not None:
            for j in range(block_from_idx, len(body)):
                pos = self.get_metadata(PositionProvider, body[j])
                self.no_mutate_lines.update(range(pos.start.line, pos.end.line + 1))
            self._close_context()

    def visit_Module(self, node: cst.Module) -> bool | None:
        self._scan_empty_lines(node.header)
        self._scan_body_stmts(node.body)
        return True

    def leave_Module(self, node: cst.Module) -> None:
        self._scan_empty_lines(node.footer)
        if self._context_type == "selection":
            raise PragmaParseError(
                f"Missing no mutate end for start block at {self.filename}:{self._context_start_line}"
            )

    def visit_SimpleStatementLine(self, node: cst.SimpleStatementLine) -> bool | None:
        tok = _parse_pragma_token(node.trailing_whitespace.comment)
        if tok is not None:
            line = self.get_metadata(PositionProvider, node).start.line
            self.no_mutate_lines.add(line)
        return True

    def _visit_compound_header(self, node: cst.CSTNode) -> None:
        body = getattr(node, "body", None)
        if isinstance(body, cst.IndentedBlock):
            tok = _parse_pragma_token(body.header.comment)
            if tok is None:
                return
            node_line = self.get_metadata(PositionProvider, node).start.line
            if tok == "block":
                body_pos = self.get_metadata(PositionProvider, body)
                self.ignore_node_lines.add(node_line)
                self.ignore_node_lines.update(range(body_pos.start.line, body_pos.end.line + 1))
            else:
                self.no_mutate_lines.add(node_line)
        elif isinstance(body, cst.SimpleStatementSuite):
            tok = _parse_pragma_token(body.trailing_whitespace.comment)
            if tok is None:
                return
            node_line = self.get_metadata(PositionProvider, node).start.line
            self.no_mutate_lines.add(node_line)

    def visit_If(self, node: cst.If) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_For(self, node: cst.For) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_While(self, node: cst.While) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_With(self, node: cst.With) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_Try(self, node: cst.Try) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_ClassDef(self, node: cst.ClassDef) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_Match(self, node: cst.CSTNode) -> bool | None:
        self._visit_compound_header(node)
        return True

    def visit_IndentedBlock(self, node: cst.IndentedBlock) -> bool | None:
        self._scan_body_stmts(node.body)
        self._scan_empty_lines(node.footer)
        return True
