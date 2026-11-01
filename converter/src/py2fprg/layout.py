"""Source layout: comment lines, `# fg:` directives, statement headers, and the `# fg: ignore` pre-pass.

Comments are not part of Python's AST, so everything that attaches them to statements works on
line numbers. The helpers here define, once, which lines belong to which statement; the converter
(comment placement) and the ignore pre-pass (directive placement) both use them.
"""
from __future__ import annotations

import ast
import bisect
import copy
import io
import re
import tokenize
from typing import Optional

DIRECTIVE_RE = re.compile(r"^\s*fg\s*:\s*([A-Za-z_-]+)\s*(.*?)\s*$", re.IGNORECASE)
KNOWN_DIRECTIVES = {"ignore", "breakpoint", "comment", "name", "title", "about", "author", "authors"}
# Comments meant for tools, not readers: kept as (empty) comment lines for layout, never emitted.
PRAGMA_RE = re.compile(r"^\s*(noqa\b|type:|pragma\b|pylint:|mypy:|pyright:|ruff:|flake8[:\s]|fmt:|isort:|nosec\b)",
                       re.IGNORECASE)
CODING_RE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")

COMPOUND = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.FunctionDef, ast.ClassDef,
            ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Match, ast.TryStar)
BLOCK_FIELDS = {"body", "orelse", "handlers", "finalbody", "decorator_list", "cases"}


def parse_directive(comment: str) -> Optional[tuple[str, str]]:
    """``# fg: ignore`` -> ("ignore", ""); ``# fg: name Guess Game`` -> ("name", "Guess Game")."""
    m = DIRECTIVE_RE.match(comment)
    if not m:
        return None
    return m.group(1).lower(), m.group(2)


def scan_source(source: str) -> tuple[dict[int, str], list[tuple[int, int]]]:
    """Comment text by line (without the '#') and the positions of all ':' tokens.

    A shebang, a PEP 263 coding line and tool pragmas (``# noqa``, ``# type: ignore``, ...) are
    recorded with empty text: they still count as comment lines, but never become Comment shapes.
    """
    comments: dict[int, str] = {}
    colons: list[tuple[int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                line = tok.start[0]
                text = tok.string[1:].rstrip()
                if (line == 1 and tok.string.startswith("#!") or line <= 2 and CODING_RE.match(tok.string)
                        or PRAGMA_RE.match(text)):
                    text = ""
                comments[line] = text
            elif tok.type == tokenize.OP and tok.string == ":":
                colons.append(tok.start)
    except (tokenize.TokenError, SyntaxError):  # pragma: no cover - ast.parse already succeeded
        pass
    return comments, colons


def indent_of(raw: str) -> int:
    return len(raw) - len(raw.lstrip())


def header_end(m, st: ast.stmt) -> int:
    """Last line of a statement's header: for a compound statement the line of the ':' that opens
    its body (headers may span lines), else the statement's last line."""
    if not isinstance(st, COMPOUND):
        return st.end_lineno or st.lineno
    pos = (st.lineno, st.col_offset)
    for name, value in ast.iter_fields(st):
        if name in BLOCK_FIELDS:
            continue
        for v in value if isinstance(value, list) else [value]:
            if isinstance(v, ast.AST):
                for n in ast.walk(v):
                    if getattr(n, "end_lineno", None) is not None:
                        pos = max(pos, (n.end_lineno, n.end_col_offset))
    i = bisect.bisect_left(m.colons, pos)
    return m.colons[i][0] if i < len(m.colons) else st.lineno


def extend_comments(m, end: int, col: int) -> int:
    """`end` extended over the comment lines that follow it (blank lines allowed) and are indented
    deeper than `col`: comments written at a block's indentation after its last statement."""
    last, ln = end, end + 1
    while ln <= len(m.lines):
        raw = m.lines[ln - 1]
        if not raw.strip():
            ln += 1
            continue
        if ln in m.comments and raw.lstrip().startswith("#") and indent_of(raw) > col:
            last = ln
            ln += 1
            continue
        break
    return last


def trailing_end(m, st: ast.stmt) -> int:
    """Last line that belongs to a statement, including the comments indented under a compound one."""
    end = st.end_lineno or st.lineno
    return extend_comments(m, end, st.col_offset) if isinstance(st, COMPOUND) else end


def find_else_line(m, col: int, start: int, end: int) -> Optional[int]:
    """Line of the `else:` keyword at indentation `col` between lines start and end."""
    for ln in range(max(start, 1), min(end, len(m.lines)) + 1):
        raw = m.lines[ln - 1]
        if indent_of(raw) == col and re.match(r"\s*else\s*:", raw):
            return ln
    return None


def is_elif(m, st: ast.stmt) -> bool:
    return (isinstance(st, ast.If) and st.lineno - 1 < len(m.lines)
            and m.lines[st.lineno - 1].lstrip().startswith("elif"))


def body_end(m, st: ast.stmt) -> int:
    """Last line of the first block (`body`) of a compound statement, with its trailing comments."""
    stmts = [s for s in st.body if isinstance(s, ast.AST)]
    end = stmts[-1].end_lineno if stmts else header_end(m, st)
    return extend_comments(m, end, st.col_offset)


class IgnorePass:
    """Removes the statements marked `# fg: ignore` before anything else looks at the code.

    A directive applies to the statement that follows it in the same block: it may sit on any line
    after the previous statement (and that statement's indented trailing comments) up to the end of
    this statement's header, i.e. above the statement, trailing its first line, or trailing any
    line of a multi-line header. On an `elif` header only that branch goes; on (or right above) an
    `else:` line the else branch goes. Returns copies, the AST itself is never changed. All lines of
    an ignored statement, and the comments above it, are added to `gone`.
    """

    def __init__(self, m, gone: set[int]):
        self.m = m
        self.gone = gone
        self.ignored: list[ast.stmt] = []  # the original nodes that were left out

    def marked(self, start: int, end: int) -> bool:
        for ln in range(start, end + 1):
            if ln not in self.gone:
                d = parse_directive(self.m.comments.get(ln, ""))
                if d and d[0] == "ignore":
                    return True
        return False

    def drop(self, start: int, end: int) -> None:
        self.gone.update(range(start, end + 1))

    def block(self, stmts: list, start_line: int) -> list:
        out: list = []
        prev_end = start_line - 1
        for st in stmts:
            end = trailing_end(self.m, st)
            if self.marked(prev_end + 1, header_end(self.m, st)):
                self.drop(prev_end + 1, end)
                self.ignored.append(st)
            else:
                out.append(self.stmt(st))
            prev_end = end
        return out

    def stmt(self, st: ast.stmt) -> ast.stmt:
        if isinstance(st, (ast.If, ast.For, ast.While)):
            new = copy.copy(st)
            new.body = self.block(st.body, header_end(self.m, st) + 1)
            new.orelse = self.orelse(st)
            return new
        return st  # other compound statements are errors (or handled by their owner)

    def orelse(self, st) -> list:
        if not st.orelse:
            return []
        start = body_end(self.m, st) + 1
        first = st.orelse[0]
        if isinstance(st, ast.If) and len(st.orelse) == 1 and is_elif(self.m, first):
            if self.marked(start, header_end(self.m, first)):
                self.drop(start, body_end(self.m, first))
                self.ignored.append(first)
                return self.orelse(first)  # the rest of the chain stays
            return [self.stmt(first)]
        else_line = find_else_line(self.m, st.col_offset, start, first.lineno) or start
        if self.marked(start, else_line):
            self.drop(start, trailing_end(self.m, st))
            self.ignored.extend(st.orelse)
            return []
        return self.block(st.orelse, else_line + 1)
