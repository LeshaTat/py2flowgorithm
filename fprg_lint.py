#!/usr/bin/env python3
"""Validator ("linter") for Flowgorithm .fprg flowchart files.

Flowgorithm stores flowcharts as XML.  This script checks that a file has the
structure Flowgorithm expects (root, attributes, functions, parameters and the
statement elements with their attributes), that identifiers are legal and
declared before use, that every expression parses under the Flowgorithm
expression grammar, that function calls have the right arity, and that operand
types are plausible.  It is a stand-in for "would Flowgorithm open and run this
file" and is deliberately strict.  The format reference is docs/fprg-format.md.

Command line:
    python3 fprg_lint.py [--strict] [--quiet] FILE [FILE ...]

Prints one line per finding
    path: function/statement-path: ERROR|WARNING: message
then a one-line summary per file, and exits 1 if any file has errors.
--strict promotes warnings to errors; --quiet prints only errors.

Library use:
    from fprg_lint import lint_file, lint_string, Finding
    findings = lint_file("prog.fprg")
    findings = lint_string(xml_text, name="generated")
Each Finding has .severity ("ERROR"/"WARNING"), .path, .message and .file.

Severity policy: anything that is certainly wrong (structure, syntax, undeclared
or duplicate names, arity, '+' on a string literal) is an ERROR; anything that
depends on inferred types or on undocumented Flowgorithm behaviour is a WARNING.

Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional, Union

__all__ = ["Finding", "lint_file", "lint_string", "lint_tree", "ERROR", "WARNING", "main"]

ERROR = "ERROR"
WARNING = "WARNING"


@dataclass
class Finding:
    severity: str
    path: str
    message: str
    file: str = ""

    def __str__(self) -> str:
        parts = [p for p in (self.file, self.path) if p]
        parts.append(self.severity)
        parts.append(self.message)
        return ": ".join(parts)


# ---------------------------------------------------------------------------
# Language tables
# ---------------------------------------------------------------------------

VALUE_TYPES = ("Integer", "Real", "String", "Boolean")
FUNCTION_TYPES = ("None",) + VALUE_TYPES
BOOL_ATTR_VALUES = ("True", "False")

KEYWORDS = {"and", "or", "not", "mod", "true", "false", "pi"}
FUTURE_RESERVED = {"arccosh", "cosh", "arcsinh", "sinh", "arctanh", "tanh"}

# display name, arity, return type ("same": the numeric type of the argument),
# argument kinds: "num" (Integer or Real), "int", "str", "any", "array"
_INTRINSIC_TABLE = [
    ("Abs", 1, "same", ("num",)),
    ("Arcsin", 1, "Real", ("num",)),
    ("Arccos", 1, "Real", ("num",)),
    ("Arctan", 1, "Real", ("num",)),
    ("Cos", 1, "Real", ("num",)),
    ("Int", 1, "Integer", ("num",)),
    ("Ln", 1, "Real", ("num",)),
    ("Log", 1, "Real", ("num",)),
    ("Log10", 1, "Real", ("num",)),
    ("Sgn", 1, "Integer", ("num",)),
    ("Sin", 1, "Real", ("num",)),
    ("Sqrt", 1, "Real", ("num",)),
    ("Tan", 1, "Real", ("num",)),
    ("Len", 1, "Integer", ("str",)),
    ("Char", 2, "String", ("str", "int")),
    ("ToChar", 1, "String", ("int",)),
    ("ToCode", 1, "Integer", ("str",)),
    ("ToFixed", 2, "String", ("num", "int")),
    ("ToInteger", 1, "Integer", ("any",)),
    ("ToReal", 1, "Real", ("any",)),
    ("ToString", 1, "String", ("any",)),
    ("EOF", 0, "Boolean", ()),
    ("Random", 1, "Integer", ("int",)),
    ("Size", 1, "Integer", ("array",)),
]
INTRINSICS = {name.lower(): (name, arity, ret, kinds) for name, arity, ret, kinds in _INTRINSIC_TABLE}

RESERVED_WORDS = KEYWORDS | {t.lower() for t in VALUE_TYPES} | set(INTRINSICS) | FUTURE_RESERVED

KNOWN_ATTRIBUTE_NAMES = ("name", "authors", "about", "saved", "created", "edited")
EXPECTED_ATTRIBUTE_NAMES = ("name", "authors", "about", "saved")

# statement element -> (required attributes, optional attributes)
STATEMENT_ATTRS = {
    "declare": (("name", "type", "array", "size"), ()),
    "assign": (("variable", "expression"), ()),
    "input": (("variable",), ()),
    "output": (("expression",), ("newline",)),
    "if": (("expression",), ()),
    "while": (("expression",), ()),
    "do": (("expression",), ()),
    "for": (("variable", "start", "end", "step"), ("direction",)),
    "call": (("expression",), ()),
    "comment": (("text",), ()),
    "breakpoint": ((), ()),
}

_IDENT_RE = re.compile(r"^[^\W\d]\w*$")           # letter, then letters/digits (any script)
_ASCII_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
_VERSION_RE = re.compile(r"^(\d+)(?:\.\d+)*$")


def identifier_problem(name: str) -> tuple[Optional[str], Optional[str]]:
    """Return (error, warning) for an identifier used as a name; both None if fine."""
    if name == "":
        return "empty identifier", None
    if "_" in name:
        return f"illegal identifier '{name}': underscores are not allowed", None
    if not _IDENT_RE.match(name):
        return (f"illegal identifier '{name}': must start with a letter followed by "
                f"letters or digits"), None
    if name.lower() in RESERVED_WORDS:
        return f"'{name}' is a reserved word and cannot be used as an identifier", None
    if not _ASCII_IDENT_RE.match(name):
        return None, f"identifier '{name}' contains non-ASCII letters; prefer plain ASCII"
    return None, None


# ---------------------------------------------------------------------------
# Expression tokenizer
# ---------------------------------------------------------------------------

class ExprError(Exception):
    def __init__(self, message: str, pos: int):
        super().__init__(message)
        self.message = message
        self.pos = pos


@dataclass
class Tok:
    kind: str   # num | str | ident | kw | op | eof
    value: str  # normalised value (keywords lower-cased, π -> pi)
    text: str   # source spelling
    pos: int    # 0-based offset in the expression


_TOKEN_RE = re.compile(r"""
    (?P<ws>[ \t\r\n]+)
  | (?P<badnum>[0-9]+\.(?![0-9])|\.[0-9]+)
  | (?P<num>[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)
  | (?P<str>"[^"]*")
  | (?P<badstr>")
  | (?P<ident>[^\W\d]\w*)
  | (?P<op><=|>=|==|!=|<>|&&|\|\||[-+*/%^&<>=!()\[\],]|[≠≤≥×÷∧∨↑¬π])
  | (?P<bad>.)
""", re.VERBOSE | re.DOTALL)


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        s = m.group()
        pos = m.start()
        if kind == "ws":
            continue
        if kind == "badnum":
            raise ExprError(f"malformed number '{s}'", pos)
        if kind == "badstr":
            raise ExprError("unterminated string literal", pos)
        if kind == "bad":
            if s == "'":
                raise ExprError("unexpected character \"'\" (string literals use double quotes)", pos)
            raise ExprError(f"unexpected character {s!r}", pos)
        if kind == "ident":
            low = s.lower()
            if s == "π":                       # a Unicode letter, so it matches as an identifier
                toks.append(Tok("kw", "pi", s, pos))
            elif low in KEYWORDS:
                toks.append(Tok("kw", low, s, pos))
            elif "_" in s:
                raise ExprError(f"illegal identifier '{s}': underscores are not allowed", pos)
            else:
                toks.append(Tok("ident", s, s, pos))
            continue
        if kind == "op":
            if s == "π":
                toks.append(Tok("kw", "pi", s, pos))
            else:
                toks.append(Tok("op", s, s, pos))
            continue
        toks.append(Tok(kind, s, s, pos))
    toks.append(Tok("eof", "", "", len(text)))
    return toks


# ---------------------------------------------------------------------------
# Expression AST and parser (precedence climbing)
# ---------------------------------------------------------------------------

@dataclass
class Num:
    text: str
    pos: int
    paren: bool = False

    @property
    def is_real(self) -> bool:
        return "." in self.text or "e" in self.text.lower()

    @property
    def value(self) -> float:
        return float(self.text)


@dataclass
class Str:
    text: str
    pos: int
    paren: bool = False


@dataclass
class Const:
    name: str  # true | false | pi
    pos: int
    paren: bool = False


@dataclass
class Var:
    name: str
    pos: int
    paren: bool = False


@dataclass
class Index:
    name: str
    index: "Node"
    pos: int
    paren: bool = False


@dataclass
class Call:
    name: str
    args: list
    pos: int
    paren: bool = False


@dataclass
class Unary:
    op: str       # neg | not
    op_text: str
    operand: "Node"
    pos: int
    paren: bool = False


@dataclass
class Binary:
    op: str       # canonical: or and < > <= >= == != & + - * / % ^
    op_text: str
    left: "Node"
    right: "Node"
    pos: int
    paren: bool = False


Node = Union[Num, Str, Const, Var, Index, Call, Unary, Binary]

OR_OPS = {"or", "||", "∨"}
AND_OPS = {"and", "&&", "∧"}
REL_OPS = {">", "<", ">=", "≥", "<=", "≤", "==", "=", "!=", "<>", "≠"}
ADD_OPS = {"+", "-"}
MUL_OPS = {"*", "×", "/", "÷", "%", "mod"}
POW_OPS = {"^", "↑"}
NOT_OPS = {"!", "not", "¬"}
CANONICAL = {
    "||": "or", "∨": "or", "&&": "and", "∧": "and",
    "≥": ">=", "≤": "<=", "=": "==", "<>": "!=", "≠": "!=",
    "×": "*", "÷": "/", "mod": "%", "↑": "^", "!": "not", "¬": "not",
}
RELATIONAL = {"<", ">", "<=", ">=", "==", "!="}
ORDERING = {"<", ">", "<=", ">="}


def _describe(tok: Tok) -> str:
    if tok.kind == "eof":
        return "end of expression"
    if tok.kind == "ident":
        return f"identifier '{tok.text}'"
    if tok.kind == "num":
        return f"number '{tok.text}'"
    if tok.kind == "str":
        return "string literal"
    if tok.kind == "kw":
        return f"keyword '{tok.text}'"
    return f"'{tok.text}'"


class Parser:
    """Parses one Flowgorithm expression; collects non-fatal warnings."""

    def __init__(self, text: str):
        self.text = text
        self.tokens = tokenize(text)
        self.i = 0
        self.warnings: list[str] = []

    # -- token helpers --
    def peek(self) -> Tok:
        return self.tokens[self.i]

    def advance(self) -> Tok:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def at(self, ops: set) -> bool:
        tok = self.peek()
        return tok.kind in ("op", "kw") and tok.value in ops

    def expect(self, op: str) -> Tok:
        tok = self.peek()
        if tok.kind == "op" and tok.value == op:
            return self.advance()
        raise ExprError(f"expected '{op}' but found {_describe(tok)}", tok.pos)

    # -- grammar --
    def parse(self) -> Node:
        node = self.parse_or()
        tok = self.peek()
        if tok.kind != "eof":
            raise ExprError(f"unexpected {_describe(tok)}", tok.pos)
        return node

    def _binary_loop(self, ops: set, sub) -> Node:
        left = sub()
        while self.at(ops):
            tok = self.advance()
            right = sub()
            left = Binary(CANONICAL.get(tok.value, tok.value), tok.text, left, right, tok.pos)
        return left

    def parse_or(self) -> Node:
        return self._binary_loop(OR_OPS, self.parse_and)

    def parse_and(self) -> Node:
        return self._binary_loop(AND_OPS, self.parse_rel)

    def parse_rel(self) -> Node:
        left = self.parse_concat()
        count = 0
        while self.at(REL_OPS):
            tok = self.advance()
            right = self.parse_concat()
            left = Binary(CANONICAL.get(tok.value, tok.value), tok.text, left, right, tok.pos)
            count += 1
        if count > 1:
            self.warnings.append("chained comparison: 'x < y < z' means '(x < y) < z' in Flowgorithm, "
                                 "a Boolean compared with a number; split it with 'and'")
        return left

    def parse_concat(self) -> Node:
        return self._binary_loop({"&"}, self.parse_add)

    def parse_add(self) -> Node:
        return self._binary_loop(ADD_OPS, self.parse_mul)

    def parse_mul(self) -> Node:
        left = self.parse_pow()
        while self.at(MUL_OPS):
            tok = self.advance()
            right = self.parse_pow()
            op = CANONICAL.get(tok.value, tok.value)
            if op in ("/", "%") and isinstance(right, Num) and right.value == 0:
                self.warnings.append(f"division by zero literal ('{tok.text} {right.text}')")
            left = Binary(op, tok.text, left, right, tok.pos)
        return left

    def parse_pow(self) -> Node:
        left = self.parse_unary()
        count = 0
        while self.at(POW_OPS):
            tok = self.advance()
            if count == 0 and isinstance(left, Unary) and left.op == "neg" and not left.paren:
                self.warnings.append(
                    f"unary minus binds tighter than '{tok.text}' in Flowgorithm: "
                    f"'-x {tok.text} y' means '(-x) {tok.text} y'; parenthesize if '-(x {tok.text} y)' was meant")
            right = self.parse_unary()
            left = Binary("^", tok.text, left, right, tok.pos)
            count += 1
        if count > 1:
            self.warnings.append("chained '^' without parentheses; its associativity is not documented")
        return left

    def parse_unary(self) -> Node:
        tok = self.peek()
        if tok.kind == "op" and tok.value == "-":
            self.advance()
            return Unary("neg", tok.text, self.parse_unary(), tok.pos)
        if self.at(NOT_OPS):
            self.advance()
            return Unary("not", tok.text, self.parse_unary(), tok.pos)
        return self.parse_primary()

    def parse_primary(self) -> Node:
        tok = self.advance()
        if tok.kind == "num":
            return Num(tok.text, tok.pos)
        if tok.kind == "str":
            return Str(tok.text[1:-1], tok.pos)
        if tok.kind == "kw":
            if tok.value in ("true", "false", "pi"):
                return Const(tok.value, tok.pos)
            raise ExprError(f"unexpected keyword '{tok.text}'", tok.pos)
        if tok.kind == "ident":
            name = tok.value
            if not _ASCII_IDENT_RE.match(name):
                self.warnings.append(f"identifier '{name}' contains non-ASCII letters; prefer plain ASCII")
            nxt = self.peek()
            if nxt.kind == "op" and nxt.value == "(":
                self.advance()
                args: list[Node] = []
                if not (self.peek().kind == "op" and self.peek().value == ")"):
                    args.append(self.parse_or())
                    while self.peek().kind == "op" and self.peek().value == ",":
                        self.advance()
                        args.append(self.parse_or())
                self.expect(")")
                return Call(name, args, tok.pos)
            if nxt.kind == "op" and nxt.value == "[":
                self.advance()
                index = self.parse_or()
                after = self.peek()
                if after.kind == "op" and after.value == ",":
                    raise ExprError("arrays are one-dimensional: only one index is allowed", after.pos)
                self.expect("]")
                after = self.peek()
                if after.kind == "op" and after.value == "[":
                    raise ExprError("arrays are one-dimensional: only one index is allowed", after.pos)
                return Index(name, index, tok.pos)
            return Var(name, tok.pos)
        if tok.kind == "op" and tok.value == "(":
            node = self.parse_or()
            self.expect(")")
            node.paren = True
            return node
        if tok.kind == "eof":
            raise ExprError("unexpected end of expression", tok.pos)
        if tok.kind == "op" and tok.value == "+":
            raise ExprError("unexpected '+' (Flowgorithm has no unary plus)", tok.pos)
        raise ExprError(f"unexpected {_describe(tok)}", tok.pos)


def parse_expression(text: str) -> Node:
    """Parse an expression; raises ExprError on a syntax error."""
    return Parser(text).parse()


# ---------------------------------------------------------------------------
# Types used by the checker
# ---------------------------------------------------------------------------
# A type is "Integer" | "Real" | "String" | "Boolean" | ("array", base) | None (unknown)

def _is_numeric(t) -> bool:
    return t in ("Integer", "Real")


def _is_array(t) -> bool:
    return isinstance(t, tuple)


def _tn(t) -> str:
    if t is None:
        return "unknown type"
    if isinstance(t, tuple):
        return f"{t[1]} array"
    return t


def _category(t):
    return "number" if _is_numeric(t) else t


def _compatible(target, value) -> bool:
    """Can a value of type `value` be stored in a scalar of type `target`?"""
    if target is None or value is None:
        return True
    if _is_array(target) or _is_array(value):
        return False
    if _is_numeric(target):
        return _is_numeric(value)        # Integer <-> Real convert implicitly
    return target == value


def _short(text: str, limit: int = 60) -> str:
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# Linter
# ---------------------------------------------------------------------------

@dataclass
class VarInfo:
    name: str
    type: str
    is_array: bool
    origin: str                 # "parameter" or the path of the declare statement
    excl: dict = field(default_factory=dict)   # {id(if element): "then"|"else"} enclosing branches


@dataclass
class FuncSig:
    name: str
    path: str
    type: str
    variable: str
    params: list
    body: Optional[ET.Element]
    registered: bool = True


class _FuncState:
    def __init__(self, sig: FuncSig):
        self.sig = sig
        self.scope: dict[str, VarInfo] = {p.name.lower(): p for p in sig.params}
        self.written: set[str] = set()
        self.declared_anywhere: set[str] = set()


def _exclusive(a: dict, b: dict) -> bool:
    """True when two declarations sit in different branches of one if statement."""
    return any(k in a and a[k] != v for k, v in b.items())


class _Linter:
    def __init__(self, file: str):
        self.file = file
        self.findings: list[Finding] = []
        self.legacy = False               # fileversion 1.x
        self.functions: dict[str, FuncSig] = {}
        self.sigs: list[FuncSig] = []
        self.called: set[str] = set()

    # -- reporting --
    def error(self, path: str, message: str) -> None:
        self.findings.append(Finding(ERROR, path, message, self.file))

    def warning(self, path: str, message: str) -> None:
        self.findings.append(Finding(WARNING, path, message, self.file))

    # -- generic element helpers --
    def _check_text(self, el: ET.Element, path: str) -> None:
        if el.text and el.text.strip():
            self.warning(path, f"stray text inside <{el.tag}>: {_short(el.text.strip())!r}")
        for child in el:
            if child.tail and child.tail.strip():
                self.warning(path, f"stray text after <{child.tag}>: {_short(child.tail.strip())!r}")

    def _check_attrs(self, el: ET.Element, path: str, required, optional) -> bool:
        ok = True
        for a in required:
            if a not in el.attrib:
                self.error(path, f"<{el.tag}> is missing required attribute '{a}'")
                ok = False
        for a in el.attrib:
            if a not in required and a not in optional:
                self.warning(path, f"unknown attribute '{a}' on <{el.tag}>")
        return ok

    def _no_children(self, el: ET.Element, path: str) -> None:
        for child in el:
            self.error(path, f"unexpected element <{child.tag}> inside <{el.tag}>")

    def _check_name(self, name: str, path: str, what: str) -> bool:
        err, warn = identifier_problem(name)
        if err:
            self.error(path, f"{what}: {err}")
            return False
        if warn:
            self.warning(path, f"{what}: {warn}")
        return True

    # -- root --
    def lint_root(self, root: ET.Element) -> None:
        if root.tag != "flowgorithm":
            self.error("", f"root element is <{root.tag}>, expected <flowgorithm>")
            return
        fv = root.get("fileversion")
        if fv is None:
            self.error("flowgorithm", "missing 'fileversion' attribute on <flowgorithm>")
        else:
            m = _VERSION_RE.match(fv.strip())
            if not m:
                self.error("flowgorithm", f"fileversion '{fv}' is not a version number")
            else:
                major = int(m.group(1))
                self.legacy = major < 2
                if major < 1 or major > 4:
                    self.warning("flowgorithm", f"fileversion '{fv}' is outside the known range (1.0 - 4.2)")
        for a in root.attrib:
            if a != "fileversion":
                self.warning("flowgorithm", f"unknown attribute '{a}' on <flowgorithm>")
        self._check_text(root, "flowgorithm")

        attribute_els = []
        function_els = []
        for child in root:
            if child.tag == "attributes":
                attribute_els.append(child)
            elif child.tag == "function":
                function_els.append(child)
            else:
                self.error("flowgorithm", f"unexpected element <{child.tag}> under <flowgorithm>")
        if not attribute_els:
            self.warning("flowgorithm", "no <attributes> element (Flowgorithm writes name/authors/about/saved)")
        elif len(attribute_els) > 1:
            self.error("flowgorithm", "more than one <attributes> element")
        for el in attribute_els:
            self._lint_attributes(el)

        if not function_els:
            self.error("flowgorithm", "no <function> elements; a program needs a Main function")
            return
        for idx, el in enumerate(function_els):
            self.sigs.append(self._collect_function(el, idx))
        if "main" not in self.functions:
            self.error("flowgorithm", "no Main function (expected <function name=\"Main\" type=\"None\" variable=\"\">)")
        for sig in self.sigs:
            self._lint_function(sig)
        for sig in self.sigs:
            low = sig.name.lower()
            if sig.registered and low != "main" and low and low not in self.called:
                self.warning(sig.path, f"function '{sig.name}' is never called")

    # -- attributes --
    def _lint_attributes(self, el: ET.Element) -> None:
        path = "attributes"
        for a in el.attrib:
            self.warning(path, f"unknown attribute '{a}' on <attributes>")
        self._check_text(el, path)
        seen: dict[str, int] = {}
        for i, child in enumerate(el):
            cpath = f"{path}/attribute[{i}]"
            if child.tag != "attribute":
                self.error(cpath, f"unexpected element <{child.tag}> inside <attributes>")
                continue
            self._check_attrs(child, cpath, ("name", "value"), ())
            self._no_children(child, cpath)
            name = child.get("name")
            if name is None:
                continue
            if name not in KNOWN_ATTRIBUTE_NAMES:
                self.warning(cpath, f"unknown program attribute '{name}'")
            seen[name] = seen.get(name, 0) + 1
            if seen[name] > 1 and name != "edited":
                self.warning(cpath, f"program attribute '{name}' given more than once")
        missing = [n for n in EXPECTED_ATTRIBUTE_NAMES if n not in seen]
        if missing:
            self.warning(path, "attributes section lacks " + ", ".join(f"'{n}'" for n in missing))

    # -- functions: pass 1 (signatures) --
    def _collect_function(self, el: ET.Element, idx: int) -> FuncSig:
        name = el.get("name")
        path = name if name else f"function[{idx}]"
        self._check_attrs(el, path, ("name", "type", "variable"), ())
        self._check_text(el, path)

        if name is not None:
            self._check_name(name, path, "function name")
        ftype = el.get("type")
        if ftype is not None and ftype not in FUNCTION_TYPES:
            hint = ""
            for t in FUNCTION_TYPES:
                if t.lower() == ftype.lower():
                    hint = f" (did you mean '{t}'?)"
            self.error(path, f"function type '{ftype}' is not one of {', '.join(FUNCTION_TYPES)}{hint}")
            ftype = None
        variable = el.get("variable") or ""
        if variable:
            self._check_name(variable, path, "return variable")
        if ftype in VALUE_TYPES and not variable:
            self.error(path, f"function '{name}' has type {ftype} but no return variable ('variable' is empty)")
        if ftype == "None" and variable:
            self.warning(path, f"function '{name}' has type None but names a return variable '{variable}'")

        params_el = None
        body_el = None
        for i, child in enumerate(el):
            if child.tag == "parameters":
                if params_el is not None:
                    self.error(path, "more than one <parameters> element")
                else:
                    params_el = child
                    if body_el is not None:
                        self.error(path, "<parameters> must precede <body>")
            elif child.tag == "body":
                if body_el is not None:
                    self.error(path, "more than one <body> element")
                else:
                    body_el = child
            else:
                self.error(path, f"unexpected element <{child.tag}> inside <function>")
        if params_el is None:
            self.error(path, "missing <parameters> element (use <parameters/> when there are none)")
        if body_el is None:
            self.error(path, "missing <body> element")

        params: list[VarInfo] = []
        if params_el is not None:
            params = self._collect_parameters(params_el, path)

        low = (name or "").lower()
        if low == "main":
            if name != "Main":
                self.warning(path, f"Main function is spelled '{name}'; Flowgorithm writes 'Main'")
            if ftype is not None and ftype != "None":
                self.error(path, f"Main must have type None, not {ftype}")
            if variable:
                self.warning(path, "Main should have an empty 'variable' attribute")
            if params:
                self.error(path, "Main cannot have parameters")

        sig = FuncSig(name or "", path, ftype or "None", variable, params, body_el)
        if name:
            if low in self.functions:
                other = self.functions[low]
                self.error(path, f"duplicate function name '{name}' (already defined as '{other.name}')")
                sig.registered = False
            else:
                self.functions[low] = sig
        return sig

    def _collect_parameters(self, el: ET.Element, fpath: str) -> list[VarInfo]:
        for a in el.attrib:
            self.warning(fpath, f"unknown attribute '{a}' on <parameters>")
        self._check_text(el, fpath)
        params: list[VarInfo] = []
        seen: dict[str, str] = {}
        for i, child in enumerate(el):
            ppath = f"{fpath}/parameters[{i}]"
            if child.tag != "parameter":
                self.error(ppath, f"unexpected element <{child.tag}> inside <parameters>")
                continue
            self._check_attrs(child, ppath, ("name", "type", "array"), ())
            self._no_children(child, ppath)
            name = child.get("name")
            ptype = child.get("type")
            array = child.get("array")
            if ptype is not None and ptype not in VALUE_TYPES:
                if ptype == "None":
                    self.error(ppath, "parameter type cannot be None")
                else:
                    self.error(ppath, f"parameter type '{ptype}' is not one of {', '.join(VALUE_TYPES)}")
                ptype = None
            if array is not None and array not in BOOL_ATTR_VALUES:
                self.error(ppath, f"parameter 'array' must be True or False, not '{array}'")
            if name is None:
                continue
            if not self._check_name(name, ppath, "parameter name"):
                continue
            if name.lower() in seen:
                self.error(ppath, f"duplicate parameter name '{name}' (also '{seen[name.lower()]}')")
                continue
            seen[name.lower()] = name
            params.append(VarInfo(name, ptype, array == "True", "parameter"))
        return params

    # -- functions: pass 2 (bodies) --
    def _lint_function(self, sig: FuncSig) -> None:
        if sig.body is None:
            return
        fs = _FuncState(sig)
        for decl in sig.body.iter("declare"):
            names = decl.get("name")
            if names is None:
                names = decl.get("variables", "")
            for n in names.split(","):
                fs.declared_anywhere.add(n.strip().lower())
        for a in sig.body.attrib:
            self.warning(f"{sig.path}/body", f"unknown attribute '{a}' on <body>")
        self._lint_block(sig.body, f"{sig.path}/body", fs, {}, 0)

        if sig.type in VALUE_TYPES and sig.variable:
            v = sig.variable
            info = fs.scope.get(v.lower())
            if info is None:
                self.error(sig.path, f"return variable '{v}' is never declared in function '{sig.name}'")
            else:
                if info.is_array:
                    self.warning(sig.path, f"return variable '{v}' is an array; function types are scalar")
                elif info.type is not None and info.type != sig.type:
                    self.warning(sig.path, f"return variable '{v}' is declared {info.type} but function "
                                           f"'{sig.name}' returns {sig.type}")
                if v.lower() not in fs.written:
                    self.warning(sig.path, f"return variable '{v}' is never assigned in function '{sig.name}'")

    def _lint_block(self, container: ET.Element, path: str, fs: _FuncState, excl: dict, depth: int) -> None:
        self._check_text(container, path)
        for i, el in enumerate(container):
            spath = f"{path}[{i}]/{el.tag}"
            if el.tag not in STATEMENT_ATTRS:
                self.error(spath, f"unknown statement element <{el.tag}>")
                continue
            getattr(self, f"_lint_{el.tag}")(el, spath, fs, excl, depth)

    # -- expressions --
    def _parse(self, text: str, path: str, what: str):
        """Parse an expression attribute, reporting syntax errors; returns (node, warnings) or None."""
        try:
            parser = Parser(text)
            node = parser.parse()
        except ExprError as e:
            self.error(path, f"syntax error in {what} '{_short(text)}' at column {e.pos + 1}: {e.message}")
            return None
        except RecursionError:
            self.error(path, f"{what} '{_short(text)}' is nested too deeply")
            return None
        return node, parser.warnings

    def _check_expression(self, text: Optional[str], path: str, fs: _FuncState, what: str):
        """Parse and type-check an expression attribute; returns its type or None."""
        if text is None:
            return None
        if text.strip() == "":
            self.error(path, f"empty {what}")
            return None
        parsed = self._parse(text, path, what)
        if parsed is None:
            return None
        node, parse_warnings = parsed
        for w in parse_warnings:
            self.warning(path, f"{what} '{_short(text)}': {w}")
        try:
            return self._infer(node, fs, path)
        except RecursionError:
            self.error(path, f"{what} '{_short(text)}' is nested too deeply")
            return None

    def _check_condition(self, text: Optional[str], path: str, fs: _FuncState, what: str) -> None:
        t = self._check_expression(text, path, fs, what)
        if t is not None and t != "Boolean":
            self.warning(path, f"{what} '{_short(text or '')}' is {_tn(t)}; expected Boolean")

    def _undeclared(self, name: str, fs: _FuncState, path: str) -> None:
        low = name.lower()
        hint = ""
        if low in self.functions:
            hint = f" ('{name}' is a function; call it with parentheses)"
        elif low in INTRINSICS:
            hint = f" ('{name}' is an intrinsic function; call it with parentheses)"
        elif low in fs.declared_anywhere:
            hint = " (it is declared later in the function; declare it before its first use)"
        self.error(path, f"undeclared variable '{name}'{hint}")

    def _infer(self, node: Node, fs: _FuncState, path: str):
        if isinstance(node, Num):
            return "Real" if node.is_real else "Integer"
        if isinstance(node, Str):
            return "String"
        if isinstance(node, Const):
            return "Real" if node.name == "pi" else "Boolean"
        if isinstance(node, Var):
            info = fs.scope.get(node.name.lower())
            if info is None:
                self._undeclared(node.name, fs, path)
                return None
            return ("array", info.type) if info.is_array else info.type
        if isinstance(node, Index):
            itype = self._infer(node.index, fs, path)
            if itype is not None and itype != "Integer":
                self.warning(path, f"index of '{node.name}[...]' is {_tn(itype)}; expected Integer")
            info = fs.scope.get(node.name.lower())
            if info is None:
                self._undeclared(node.name, fs, path)
                return None
            if not info.is_array:
                self.error(path, f"'{node.name}' is a {_tn(info.type)} variable, not an array, and cannot be indexed")
                return None
            return info.type
        if isinstance(node, Call):
            return self._check_call(node, fs, path, as_statement=False)
        if isinstance(node, Unary):
            t = self._infer(node.operand, fs, path)
            if node.op == "neg":
                if t is not None and not _is_numeric(t):
                    self.warning(path, f"unary '-' applied to {_tn(t)}; expected a number")
                    return None
                return t
            if t is not None and t != "Boolean":
                self.warning(path, f"'{node.op_text}' applied to {_tn(t)}; expected Boolean")
            return "Boolean"
        if isinstance(node, Binary):
            return self._infer_binary(node, fs, path)
        return None  # pragma: no cover

    def _infer_binary(self, node: Binary, fs: _FuncState, path: str):
        lt = self._infer(node.left, fs, path)
        rt = self._infer(node.right, fs, path)
        op = node.op
        sides = ((node.left, lt), (node.right, rt))

        if op in ("or", "and"):
            for _, t in sides:
                if t is not None and t != "Boolean":
                    self.warning(path, f"operand of '{node.op_text}' is {_tn(t)}; expected Boolean")
            return "Boolean"

        if op in RELATIONAL:
            # a chained comparison was already reported by the parser; do not pile on
            chained = isinstance(node.left, Binary) and node.left.op in RELATIONAL and not node.left.paren
            if not chained:
                for _, t in sides:
                    if _is_array(t):
                        self.warning(path, f"operand of '{node.op_text}' is an array; index it first")
                    elif op in ORDERING and t == "Boolean":
                        self.warning(path, f"operand of '{node.op_text}' is Boolean; ordering comparisons need "
                                           f"numbers or strings")
                if lt is not None and rt is not None and not _is_array(lt) and not _is_array(rt) \
                        and _category(lt) != _category(rt):
                    self.warning(path, f"'{node.op_text}' compares {_tn(lt)} with {_tn(rt)}")
            return "Boolean"

        if op == "&":
            for _, t in sides:
                if _is_array(t):
                    self.warning(path, f"operand of '&' is an array; index it first")
            return "String"

        # arithmetic: + - * / % ^
        if op == "+":
            literal = [n for n, _ in sides if isinstance(n, Str)]
            if literal:
                self.error(path, "'+' with a string literal operand: in Flowgorithm '+' is numeric only; "
                                 "use '&' to concatenate")
            else:
                for _, t in sides:
                    if t == "String":
                        self.warning(path, "'+' with a String operand: in Flowgorithm '+' is numeric only; "
                                           "use '&' to concatenate")
                    elif t is not None and not _is_numeric(t):
                        self.warning(path, f"operand of '+' is {_tn(t)}; expected a number")
        else:
            for _, t in sides:
                if t is not None and not _is_numeric(t):
                    self.warning(path, f"operand of '{node.op_text}' is {_tn(t)}; expected a number")
        if op == "/":
            return "Real"
        if lt == "Integer" and rt == "Integer":
            return "Integer"
        if _is_numeric(lt) and _is_numeric(rt):
            return "Real"
        return None

    def _check_call(self, node: Call, fs: _FuncState, path: str, as_statement: bool):
        name = node.name
        low = name.lower()
        n = len(node.args)

        if low in INTRINSICS:
            display, arity, ret, kinds = INTRINSICS[low]
            if as_statement:
                self.error(path, f"call must invoke a user-defined function; '{display}' is an intrinsic function")
            if n != arity:
                self.error(path, f"{display}() takes {arity} argument{'s' if arity != 1 else ''}, got {n}")
            arg_types = [self._infer(a, fs, path) for a in node.args]
            for i, (kind, t) in enumerate(zip(kinds, arg_types), start=1):
                if t is None:
                    continue
                bad = None
                if kind == "num" and not _is_numeric(t):
                    bad = "a number"
                elif kind == "int" and t != "Integer":
                    bad = "an Integer"
                elif kind == "str" and t != "String":
                    bad = "a String"
                elif kind == "array" and not _is_array(t):
                    bad = "an array"
                elif kind == "any" and _is_array(t):
                    bad = "a scalar"
                if bad:
                    self.warning(path, f"argument {i} of {display}() is {_tn(t)}; expected {bad}")
            if ret == "same":
                return arg_types[0] if arg_types and _is_numeric(arg_types[0]) else None
            return ret

        sig = self.functions.get(low)
        if sig is not None:
            self.called.add(low)
            if n != len(sig.params):
                self.error(path, f"function '{sig.name}' takes {len(sig.params)} "
                                 f"parameter{'s' if len(sig.params) != 1 else ''}, got {n}")
            arg_types = [self._infer(a, fs, path) for a in node.args]
            for i, (p, t) in enumerate(zip(sig.params, arg_types), start=1):
                if t is None:
                    continue
                if p.is_array and not _is_array(t):
                    self.warning(path, f"argument {i} of '{sig.name}': parameter '{p.name}' is an array; got {_tn(t)}")
                elif not p.is_array and _is_array(t):
                    self.warning(path, f"argument {i} of '{sig.name}': parameter '{p.name}' is {_tn(p.type)}; "
                                       f"got an array")
                elif not p.is_array and p.type is not None and not _compatible(p.type, t):
                    self.warning(path, f"argument {i} of '{sig.name}': parameter '{p.name}' is {p.type}; got {_tn(t)}")
            if as_statement:
                if sig.type != "None":
                    self.warning(path, f"call discards the {sig.type} value returned by '{sig.name}'")
                return None
            if sig.type == "None":
                self.error(path, f"function '{sig.name}' has type None (no return value) and cannot be used "
                                 f"in an expression")
                return None
            return sig.type

        if low in fs.scope:
            self.error(path, f"'{name}' is a variable, not a function")
        else:
            self.error(path, f"unknown function '{name}'")
        for a in node.args:
            self._infer(a, fs, path)
        return None

    # -- assignment / input / for targets --
    def _resolve_target(self, text: Optional[str], path: str, fs: _FuncState, what: str):
        """Parse `x` or `x[i]`; returns (VarInfo, element type, is_indexed) or (None, None, False)."""
        if text is None:
            return None, None, False
        if text.strip() == "":
            self.error(path, f"empty {what}")
            return None, None, False
        try:
            node = Parser(text).parse()
        except ExprError as e:
            self.error(path, f"{what} '{_short(text)}' is not a variable or array element: {e.message}")
            return None, None, False
        except RecursionError:
            self.error(path, f"{what} '{_short(text)}' is nested too deeply")
            return None, None, False
        if not isinstance(node, (Var, Index)) or node.paren:
            self.error(path, f"{what} '{_short(text)}' must be a variable name or an array element 'name[index]'")
            return None, None, False
        info = fs.scope.get(node.name.lower())
        if info is None:
            self._undeclared(node.name, fs, path)
            return None, None, isinstance(node, Index)
        if isinstance(node, Index):
            itype = self._infer(node.index, fs, path)
            if itype is not None and itype != "Integer":
                self.warning(path, f"index of '{node.name}[...]' is {_tn(itype)}; expected Integer")
            if not info.is_array:
                self.error(path, f"'{node.name}' is a {_tn(info.type)} variable, not an array, and cannot be indexed")
                return info, None, True
            return info, info.type, True
        if info.is_array:
            return info, ("array", info.type), False
        return info, info.type, False

    # -- statements --
    def _lint_declare(self, el, path, fs, excl, depth) -> None:
        attrs = el.attrib
        names_attr = attrs.get("name")
        if "variables" in attrs:
            self.warning(path, "legacy attribute 'variables' (Flowgorithm 1.x); modern files use 'name'")
            if names_attr is None:
                names_attr = attrs["variables"]
            elif names_attr.strip() != attrs["variables"].strip():
                self.error(path, f"'name' ({names_attr!r}) and legacy 'variables' ({attrs['variables']!r}) disagree")
        required = ["type"] if self.legacy else ["type", "array", "size"]
        if names_attr is None:
            required.insert(0, "name")
        for a in required:
            if a not in attrs:
                self.error(path, f"<declare> is missing required attribute '{a}'")
        for a in attrs:
            if a not in ("name", "type", "array", "size", "variables"):
                self.warning(path, f"unknown attribute '{a}' on <declare>")
        self._no_children(el, path)

        dtype = attrs.get("type")
        if dtype is not None and dtype not in VALUE_TYPES:
            if dtype == "None":
                self.error(path, "declared type cannot be None")
            else:
                hint = ""
                for t in VALUE_TYPES:
                    if t.lower() == dtype.lower():
                        hint = f" (did you mean '{t}'?)"
                self.error(path, f"declared type '{dtype}' is not one of {', '.join(VALUE_TYPES)}{hint}")
            dtype = None

        array = attrs.get("array", "False")
        if array not in BOOL_ATTR_VALUES:
            self.error(path, f"'array' must be True or False, not '{array}'")
        is_array = array == "True"
        size = attrs.get("size", "")
        if is_array:
            if size.strip() == "":
                self.error(path, "array declaration requires a non-empty 'size' expression")
            else:
                st = self._check_expression(size, path, fs, "array size")
                if st is not None and st != "Integer":
                    self.warning(path, f"array size '{_short(size)}' is {_tn(st)}; expected Integer")
        elif size.strip() != "":
            self.warning(path, f"'size' is given ('{_short(size)}') but 'array' is False")

        if depth > 0:
            shown = f" '{_short(names_attr.strip())}'" if names_attr is not None else ""
            self.warning(path, f"variable{shown} declared inside a block (then/else or loop body); "
                               f"declare variables at the top of the function")

        if names_attr is None:
            return
        raw_names = names_attr.split(",")
        if is_array and len(raw_names) > 1:
            self.warning(path, "array declaration with several names; the format reference shows one name per "
                               "array declare")
        for raw in raw_names:
            name = raw.strip()
            if name == "":
                self.error(path, f"empty name in declare list '{names_attr}'")
                continue
            if not self._check_name(name, path, "variable name"):
                continue
            low = name.lower()
            existing = fs.scope.get(low)
            if existing is not None:
                if existing.origin == "parameter":
                    self.error(path, f"'{name}' is already declared as a parameter")
                    continue
                if not _exclusive(existing.excl, excl):
                    self.error(path, f"duplicate declaration of '{name}' (first declared at {existing.origin})")
                    continue
            fs.scope[low] = VarInfo(name, dtype, is_array, path, dict(excl))

    def _lint_assign(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["assign"])
        self._no_children(el, path)
        info, ttype, indexed = self._resolve_target(el.get("variable"), path, fs, "assignment target")
        vtype = self._check_expression(el.get("expression"), path, fs, "expression")
        if info is not None:
            fs.written.add(info.name.lower())
            if _is_array(ttype):
                self.warning(path, f"assignment to array '{info.name}' without an index")
            elif not _compatible(ttype, vtype):
                self.warning(path, f"assigning {_tn(vtype)} to '{el.get('variable')}' which is {_tn(ttype)}")

    def _lint_input(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["input"])
        self._no_children(el, path)
        info, ttype, indexed = self._resolve_target(el.get("variable"), path, fs, "input target")
        if info is not None:
            fs.written.add(info.name.lower())
            if _is_array(ttype):
                self.warning(path, f"input into array '{info.name}' without an index")

    def _lint_output(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["output"])
        self._no_children(el, path)
        t = self._check_expression(el.get("expression"), path, fs, "expression")
        if _is_array(t):
            self.warning(path, "output of an array variable without an index")
        newline = el.get("newline")
        if newline is not None and newline not in BOOL_ATTR_VALUES:
            self.error(path, f"'newline' must be True or False, not '{newline}'")

    def _lint_if(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["if"])
        self._check_text(el, path)
        self._check_condition(el.get("expression"), path, fs, "condition")
        then_el = else_el = None
        order = []
        for child in el:
            if child.tag == "then":
                if then_el is not None:
                    self.error(path, "more than one <then> in <if>")
                else:
                    then_el = child
                    order.append("then")
            elif child.tag == "else":
                if else_el is not None:
                    self.error(path, "more than one <else> in <if>")
                else:
                    else_el = child
                    order.append("else")
            else:
                self.error(path, f"unexpected element <{child.tag}> inside <if> (only <then> and <else> are allowed)")
        if then_el is None:
            self.error(path, "<if> is missing its <then> element (use <then/> when empty)")
        if else_el is None:
            self.error(path, "<if> is missing its <else> element (use <else/> when empty)")
        if order == ["else", "then"]:
            self.error(path, "<then> must come before <else>")
        for branch, branch_el in (("then", then_el), ("else", else_el)):
            if branch_el is None:
                continue
            for a in branch_el.attrib:
                self.warning(path, f"unknown attribute '{a}' on <{branch}>")
            branch_excl = dict(excl)
            branch_excl[id(el)] = branch
            self._lint_block(branch_el, f"{path}/{branch}", fs, branch_excl, depth + 1)

    def _lint_while(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["while"])
        self._check_condition(el.get("expression"), path, fs, "condition")
        self._lint_block(el, path, fs, excl, depth + 1)

    def _lint_do(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["do"])
        self._check_condition(el.get("expression"), path, fs, "condition")
        self._lint_block(el, path, fs, excl, depth + 1)

    def _lint_for(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["for"])
        info, ttype, indexed = self._resolve_target(el.get("variable"), path, fs, "loop variable")
        if info is not None:
            fs.written.add(info.name.lower())
            if _is_array(ttype):
                self.error(path, f"loop variable '{info.name}' is an array; use an Integer variable")
            elif ttype == "Real":
                self.warning(path, f"loop variable '{el.get('variable')}' is Real; Flowgorithm loop counters "
                                   f"should be Integer")
            elif ttype in ("String", "Boolean"):
                self.error(path, f"loop variable '{el.get('variable')}' is {ttype}; it must be Integer")
        for attr in ("start", "end", "step"):
            text = el.get(attr)
            t = self._check_expression(text, path, fs, f"'{attr}' expression")
            if t is not None and not _is_numeric(t):
                self.warning(path, f"'{attr}' expression '{_short(text or '')}' is {_tn(t)}; expected a number")
        step = el.get("step")
        if step is not None and step.strip():
            try:
                node = Parser(step).parse()
            except (ExprError, RecursionError):
                node = None
            if isinstance(node, Num) and node.value <= 0:
                self.error(path, f"'step' must be a positive number, not '{step.strip()}' "
                                 f"(use direction=\"dec\" to count down)")
            elif isinstance(node, Unary) and node.op == "neg" and isinstance(node.operand, Num):
                self.error(path, f"'step' must be positive, not '{step.strip()}' (use direction=\"dec\" to count down)")
        direction = el.get("direction")
        if direction is not None and direction not in ("inc", "dec"):
            self.error(path, f"'direction' must be 'inc' or 'dec', not '{direction}'")
        self._lint_block(el, path, fs, excl, depth + 1)

    def _lint_call(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["call"])
        self._no_children(el, path)
        text = el.get("expression")
        if text is None:
            return
        if text.strip() == "":
            self.error(path, "empty call expression")
            return
        parsed = self._parse(text, path, "call expression")
        if parsed is None:
            return
        node, parse_warnings = parsed
        for w in parse_warnings:
            self.warning(path, f"call expression '{_short(text)}': {w}")
        if not isinstance(node, Call) or node.paren:
            self.error(path, f"call expression '{_short(text)}' must be a function call 'Name(arguments)' "
                             f"of a user-defined function")
            self._infer(node, fs, path)
            return
        self._check_call(node, fs, path, as_statement=True)

    def _lint_comment(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["comment"])
        self._no_children(el, path)

    def _lint_breakpoint(self, el, path, fs, excl, depth) -> None:
        self._check_attrs(el, path, *STATEMENT_ATTRS["breakpoint"])
        self._no_children(el, path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lint_tree(root: ET.Element, name: str = "<tree>") -> list[Finding]:
    """Lint an already parsed XML tree."""
    linter = _Linter(name)
    linter.lint_root(root)
    return linter.findings


def lint_string(xml_text: Union[str, bytes], name: str = "<string>") -> list[Finding]:
    """Lint .fprg XML given as a string (or bytes)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return [Finding(ERROR, "", f"not well-formed XML: {e}", name)]
    return lint_tree(root, name)


def lint_file(path: str) -> list[Finding]:
    """Lint one .fprg file; I/O problems are reported as findings."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as e:
        return [Finding(ERROR, "", f"cannot read file: {e.strerror or e}", path)]
    return lint_string(data, path)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fprg_lint.py",
        description="Validate Flowgorithm .fprg flowchart files (structure, identifiers, expressions).")
    ap.add_argument("files", nargs="+", metavar="FILE", help=".fprg file(s) to check")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--quiet", action="store_true", help="print only errors")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

    any_errors = False
    files_with_errors = 0
    for path in args.files:
        findings = lint_file(path)
        if args.strict:
            for f in findings:
                f.severity = ERROR
        n_err = sum(1 for f in findings if f.severity == ERROR)
        n_warn = len(findings) - n_err
        for f in findings:
            if args.quiet and f.severity != ERROR:
                continue
            print(f)
        if n_err:
            any_errors = True
            files_with_errors += 1
        if not args.quiet or n_err:
            print(f"{path}: {_plural(n_err, 'error')}, {_plural(n_warn, 'warning')}")
    if len(args.files) > 1 and not args.quiet:
        print(f"{_plural(len(args.files), 'file')} checked, {files_with_errors} with errors")
    return 1 if any_errors else 0


if __name__ == "__main__":
    sys.exit(main())
