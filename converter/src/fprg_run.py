#!/usr/bin/env python3
"""fprg_run - a headless interpreter for Flowgorithm ``.fprg`` flowcharts.

Flowgorithm (http://www.flowgorithm.org) only runs on Windows. This module executes
a ``.fprg`` file directly from its XML so that a flowchart can be run - and compared
with the program it was generated from - on any machine::

    python3 fprg_run.py prog.fprg --input 3 --input 4            # scripted answers
    python3 fprg_run.py prog.fprg < answers.txt                   # or from stdin
    python3 fprg_run.py prog.fprg --random 3,5,1 --vars           # fixed Random() values

    from fprg_run import run_string, run_file, Machine, evaluate
    text = run_file("prog.fprg", ["3", "4"])                      # the console output
    m = Machine(xml, ["3"], random_values=[41]); m.run(); m.variables["secret"]

Supported: every statement of the format reference (``docs/fprg-format.md``):
declare (scalars, comma lists, arrays), assign (also to ``arr[i]``), input (also into
``arr[i]``), output (``newline`` True/False, default True), if/then/else, while, do
(body first, repeats WHILE the condition holds), for (inclusive end, ``direction``
inc/dec, ``step``), call, comment and breakpoint (no-ops); functions with typed
parameters (arrays are passed by reference), the return variable, recursion; the
full expression grammar with its eight precedence levels in the C-family, BASIC-family
and Unicode spellings; all intrinsic functions; legacy 1.x files (``<declare
variables="n">``, ``<output>`` without ``newline``, ``<for>`` without ``direction``).

Everything that Flowgorithm would reject at run time (undeclared variable, unknown
function, wrong arity, bad index, type mismatch, division by zero, bad input text,
running out of input, more than ``max_steps`` statements) raises ``FprgRuntimeError``
with the function name and the statement path (``Main/body[3]/while[1]/assign``, the
same path style as ``fprg_lint.py``).

Semantics that had to be guessed
--------------------------------
Flowgorithm's run-time behaviour is not documented and could not be checked against the
real program on this machine, so the following are best guesses, chosen to agree with
Flowgorithm's documentation where it exists and with its .NET implementation otherwise:

* **Real output formatting.** A whole-valued Real prints like an integer (``3``, not
  ``3.0``), which is what Flowgorithm's console shows; any other Real prints as the
  shortest text that round-trips (``2.5``, ``0.1``, ``12.566370614359172``), with an
  upper-case exponent marker (``1E+16``) as .NET prints it. Flowgorithm builds on the
  classic .NET Framework may show at most 15 significant digits instead
  (``12.5663706143592``), so differential tests should not depend on the last digits
  of a non-terminating Real. From magnitude 1e15 on a Real is written with an exponent
  (``1E+15``, ``-1.5E+15``), as .NET does. Booleans print as ``true``/``false``.
* ``&`` and ``ToString`` use that same formatting.
* ``/`` always yields a Real. ``%``/``mod`` is a remainder with the sign of the
  dividend (as in C#/VB.NET), also for Reals. ``^`` yields an Integer when both operands
  are Integers and the exponent is not negative, otherwise a Real. Integers are
  unbounded (Flowgorithm's are fixed-width, so very large values would differ).
  ``a ^ b ^ c`` is evaluated left to right; Flowgorithm's associativity is undocumented.
* ``and``/``or`` short-circuit (the right operand is not evaluated when the left one
  decides the result); operands must be Boolean.
* Comparisons: numbers with numbers (Integer and Real mix freely), Strings with Strings
  by code point, Booleans only with ``==``/``!=``; anything else is a type error.
* A ``for`` loop evaluates start, end and step once, assigns start to the variable,
  runs while ``variable <= end`` (``>= end`` for ``dec``) and adds (subtracts) step
  after each pass; the body may change the variable, and after the loop it holds the
  first value that failed the test. ``step`` must be positive.
* Executing a ``declare`` again (for instance inside a loop body) re-initialises the
  variable; arrays are re-created with the current size.
* Assigning a Real to an Integer variable (or parameter) truncates toward zero; an
  Integer assigned to a Real converts; any other mismatch is an error.
* ``Int`` truncates toward zero. ``Ln`` and ``Log`` are both the natural logarithm,
  ``Log10`` the common one (matching .NET's ``Math.Log``). ``ToFixed`` rounds like
  Python's ``format`` (round-half-even on the binary value). ``Random(n)`` is an
  integer in ``0 .. n-1``; ``EOF()`` is always ``true`` (there is no file input).
* Input: Integer accepts only integer text (``"3.0"`` is rejected), Real any float
  text, Boolean ``true``/``false`` case-insensitively, String the line as typed;
  surrounding blanks are ignored for the three converted types.
"""
from __future__ import annotations

import argparse
import math
import os
import random as _random
import re
import sys
import xml.etree.ElementTree as ET
from typing import Callable, Iterable, Iterator, Optional, Sequence, Union

__all__ = ["FprgRuntimeError", "FprgSyntaxError", "Machine", "Program", "FArray", "run_string",
           "run_file", "evaluate", "format_value", "load_program", "main"]

INTEGER, REAL, STRING, BOOLEAN = "Integer", "Real", "String", "Boolean"
VALUE_TYPES = (INTEGER, REAL, STRING, BOOLEAN)
DEFAULTS = {INTEGER: 0, REAL: 0.0, STRING: "", BOOLEAN: False}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FprgRuntimeError(Exception):
    """Anything that stops the flowchart: a bad file, a bad expression or a run-time error.

    ``message`` is the bare problem, ``function`` and ``path`` say where it happened
    (``path`` is in the style ``Main/body[3]/while[1]/assign``); ``str(error)`` has all three.
    """

    def __init__(self, message: str, *, function: Optional[str] = None, path: Optional[str] = None):
        self.message = message
        self.function = function
        self.path = path
        super().__init__(message)

    def located(self, function: Optional[str], path: Optional[str]) -> "FprgRuntimeError":
        if self.path is None:
            self.function = function
            self.path = path
        return self

    def __str__(self) -> str:
        where = []
        if self.function is not None:
            where.append(f"in function {self.function}")
        if self.path is not None:
            where.append(f"at {self.path}")
        return self.message + (f" ({', '.join(where)})" if where else "")


class FprgSyntaxError(FprgRuntimeError):
    """A malformed .fprg file or an expression that does not parse."""


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

class FArray(list):
    """A Flowgorithm array: a list that knows its element type (passed by reference)."""
    __slots__ = ("etype",)

    def __init__(self, items: Iterable = (), etype: str = INTEGER):
        super().__init__(items)
        self.etype = etype

    def __repr__(self) -> str:
        return f"FArray({list.__repr__(self)}, {self.etype!r})"


def type_name(value) -> str:
    """The Flowgorithm type of a run-time value, for messages and checks."""
    t = type(value)
    if t is bool:
        return BOOLEAN
    if t is int:
        return INTEGER
    if t is float:
        return REAL
    if t is str:
        return STRING
    if isinstance(value, FArray):
        return f"{value.etype} array"
    if value is None:
        return "nothing (a None function has no value)"
    return t.__name__


def _is_number(value) -> bool:
    t = type(value)
    return t is int or t is float


def _describe(value) -> str:
    if type(value) is str:
        return f'String "{value}"'
    if isinstance(value, FArray):
        return type_name(value)
    if value is None:
        return type_name(value)
    return f"{type_name(value)} {format_value(value)}"


def format_value(value) -> str:
    """Console text of a value, as Output, ``&`` and ToString produce it (see module docstring)."""
    t = type(value)
    if t is bool:
        return "true" if value else "false"
    if t is int:
        return str(value)
    if t is float:
        if value != value:
            return "NaN"
        if value in (math.inf, -math.inf):
            return "Infinity" if value > 0 else "-Infinity"
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        text = repr(value)
        if "e" not in text and abs(value) >= 1e15:  # .NET uses an exponent from 1E+15 on, Python from 1e+16
            sign, digits = ("-", text[1:]) if text[0] == "-" else ("", text)
            whole, _, fraction = digits.partition(".")
            figures = (whole + fraction).rstrip("0")
            text = f"{sign}{figures[0]}{'.' + figures[1:] if len(figures) > 1 else ''}e+{len(whole) - 1:02d}"
        return text.replace("e", "E")
    if t is str:
        return value
    if isinstance(value, FArray):
        raise FprgRuntimeError("an array cannot be converted to text; index an element")
    if value is None:
        raise FprgRuntimeError("a None function has no value to convert to text")
    raise FprgRuntimeError(f"cannot format a value of type {t.__name__}")


def coerce(value, vtype: str, what: str):
    """Convert ``value`` for storing into something of type ``vtype`` (Flowgorithm's assignment rules)."""
    t = type(value)
    if vtype == INTEGER:
        if t is int:
            return value
        if t is float:
            if value != value or value in (math.inf, -math.inf):
                raise FprgRuntimeError(f"cannot assign {format_value(value)} to {what} (Integer)")
            return int(value)  # truncates toward zero
    elif vtype == REAL:
        if t is int or t is float:
            try:
                return float(value)
            except OverflowError:
                raise FprgRuntimeError(f"{value} is too large for {what} of type Real") from None
    elif vtype == STRING:
        if t is str:
            return value
    elif vtype == BOOLEAN:
        if t is bool:
            return value
    raise FprgRuntimeError(f"cannot assign {_describe(value)} to {what} of type {vtype}")


_INT_TEXT = re.compile(r"[+-]?[0-9]+")


def convert_input(text: str, vtype: str, what: str):
    """Convert one typed line to the type of the Input target."""
    if text.endswith("\n"):
        text = text[:-1]
    if text.endswith("\r"):
        text = text[:-1]
    if vtype == STRING:
        return text
    s = text.strip()
    if vtype == INTEGER:
        if _INT_TEXT.fullmatch(s):
            return int(s)
        raise FprgRuntimeError(f"input {text!r} is not an Integer ({what})")
    if vtype == REAL:
        try:
            return float(s)
        except ValueError:
            raise FprgRuntimeError(f"input {text!r} is not a Real ({what})") from None
    if vtype == BOOLEAN:
        low = s.lower()
        if low in ("true", "false"):
            return low == "true"
        raise FprgRuntimeError(f"input {text!r} is not a Boolean (true/false) ({what})")
    raise FprgRuntimeError(f"cannot input into {what} of type {vtype}")


# ---------------------------------------------------------------------------
# Expressions: tokenizer and parser (precedence climbing, eight levels)
# ---------------------------------------------------------------------------

KEYWORDS = {"and", "or", "not", "mod", "true", "false", "pi"}

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

# AST nodes are tuples whose first element is the tag:
#   ("num", value) ("str", text) ("bool", value) ("pi",)
#   ("var", name, lower) ("index", name, lower, index_node) ("call", name, lower, [args])
#   ("neg", x) ("not", x) ("and", l, r) ("or", l, r) ("bin", op, l, r)
Node = tuple


class _Tok:
    __slots__ = ("kind", "value", "text", "pos")

    def __init__(self, kind: str, value: str, text: str, pos: int):
        self.kind, self.value, self.text, self.pos = kind, value, text, pos


def _tokenize(text: str) -> list:
    toks = []
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        s = m.group()
        pos = m.start()
        if kind == "ws":
            continue
        if kind == "badnum":
            raise FprgSyntaxError(f"malformed number '{s}' at column {pos + 1}")
        if kind == "badstr":
            raise FprgSyntaxError(f"unterminated string literal at column {pos + 1}")
        if kind == "bad":
            raise FprgSyntaxError(f"unexpected character {s!r} at column {pos + 1}")
        if kind == "ident":
            low = s.lower()
            if s == "π":
                toks.append(_Tok("kw", "pi", s, pos))
            elif low in KEYWORDS:
                toks.append(_Tok("kw", low, s, pos))
            elif "_" in s:
                raise FprgSyntaxError(f"illegal identifier '{s}' at column {pos + 1}: "
                                      f"Flowgorithm identifiers cannot contain underscores")
            else:
                toks.append(_Tok("ident", s, s, pos))
        elif kind == "op":
            toks.append(_Tok("kw", "pi", s, pos) if s == "π" else _Tok("op", s, s, pos))
        else:
            toks.append(_Tok(kind, s, s, pos))
    toks.append(_Tok("eof", "", "", len(text)))
    return toks


def _tok_desc(tok: _Tok) -> str:
    if tok.kind == "eof":
        return "end of expression"
    return f"'{tok.text}'"


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = _tokenize(text)
        self.i = 0

    def peek(self) -> _Tok:
        return self.toks[self.i]

    def advance(self) -> _Tok:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def at(self, ops) -> bool:
        tok = self.toks[self.i]
        return tok.kind in ("op", "kw") and tok.value in ops

    def expect(self, op: str) -> None:
        tok = self.peek()
        if tok.kind == "op" and tok.value == op:
            self.i += 1
            return
        raise FprgSyntaxError(f"expected '{op}' but found {_tok_desc(tok)} at column {tok.pos + 1}")

    def parse(self) -> Node:
        node = self.parse_or()
        tok = self.peek()
        if tok.kind != "eof":
            raise FprgSyntaxError(f"unexpected {_tok_desc(tok)} at column {tok.pos + 1}")
        return node

    def parse_or(self) -> Node:
        left = self.parse_and()
        while self.at(OR_OPS):
            self.advance()
            left = ("or", left, self.parse_and())
        return left

    def parse_and(self) -> Node:
        left = self.parse_rel()
        while self.at(AND_OPS):
            self.advance()
            left = ("and", left, self.parse_rel())
        return left

    def parse_rel(self) -> Node:
        left = self.parse_concat()
        while self.at(REL_OPS):
            tok = self.advance()
            left = ("bin", CANONICAL.get(tok.value, tok.value), left, self.parse_concat())
        return left

    def parse_concat(self) -> Node:
        left = self.parse_add()
        while self.at({"&"}):
            self.advance()
            left = ("bin", "&", left, self.parse_add())
        return left

    def parse_add(self) -> Node:
        left = self.parse_mul()
        while self.at(ADD_OPS):
            tok = self.advance()
            left = ("bin", tok.value, left, self.parse_mul())
        return left

    def parse_mul(self) -> Node:
        left = self.parse_pow()
        while self.at(MUL_OPS):
            tok = self.advance()
            left = ("bin", CANONICAL.get(tok.value, tok.value), left, self.parse_pow())
        return left

    def parse_pow(self) -> Node:
        left = self.parse_unary()
        while self.at(POW_OPS):
            self.advance()
            left = ("bin", "^", left, self.parse_unary())
        return left

    def parse_unary(self) -> Node:
        tok = self.peek()
        if tok.kind == "op" and tok.value == "-":
            self.advance()
            return ("neg", self.parse_unary())
        if self.at(NOT_OPS):
            self.advance()
            return ("not", self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Node:
        tok = self.advance()
        if tok.kind == "num":
            text = tok.text
            if "." in text or "e" in text or "E" in text:
                return ("num", float(text))
            return ("num", int(text))
        if tok.kind == "str":
            return ("str", tok.text[1:-1])
        if tok.kind == "kw":
            if tok.value == "true":
                return ("bool", True)
            if tok.value == "false":
                return ("bool", False)
            if tok.value == "pi":
                return ("pi",)
            raise FprgSyntaxError(f"unexpected keyword '{tok.text}' at column {tok.pos + 1}")
        if tok.kind == "ident":
            name = tok.value
            nxt = self.peek()
            if nxt.kind == "op" and nxt.value == "(":
                self.advance()
                args = []
                if not (self.peek().kind == "op" and self.peek().value == ")"):
                    args.append(self.parse_or())
                    while self.peek().kind == "op" and self.peek().value == ",":
                        self.advance()
                        args.append(self.parse_or())
                self.expect(")")
                return ("call", name, name.lower(), args)
            if nxt.kind == "op" and nxt.value == "[":
                self.advance()
                index = self.parse_or()
                self.expect("]")
                return ("index", name, name.lower(), index)
            return ("var", name, name.lower())
        if tok.kind == "op" and tok.value == "(":
            node = self.parse_or()
            self.expect(")")
            return node
        if tok.kind == "eof":
            raise FprgSyntaxError("unexpected end of expression")
        if tok.kind == "op" and tok.value == "+":
            raise FprgSyntaxError(f"unexpected '+' at column {tok.pos + 1} (Flowgorithm has no unary plus)")
        raise FprgSyntaxError(f"unexpected {_tok_desc(tok)} at column {tok.pos + 1}")


def parse_expression(text: str) -> Node:
    """Parse one Flowgorithm expression into an AST; raises FprgSyntaxError."""
    try:
        return _Parser(text).parse()
    except FprgSyntaxError as e:
        raise FprgSyntaxError(f"syntax error in expression '{text}': {e.message}") from None
    except RecursionError:
        raise FprgSyntaxError(f"expression '{text}' is nested too deeply") from None


# ---------------------------------------------------------------------------
# Program model (loaded once from the XML, expressions pre-parsed)
# ---------------------------------------------------------------------------

class Target:
    """An assignment / input target: a variable or an array element ``name[index]``."""
    __slots__ = ("name", "lower", "index", "text")

    def __init__(self, name: str, index: Optional[Node], text: str):
        self.name, self.lower, self.index, self.text = name, name.lower(), index, text


def parse_target(text: str, what: str) -> Target:
    node = parse_expression(text)
    if node[0] == "var":
        return Target(node[1], None, text)
    if node[0] == "index":
        return Target(node[1], node[3], text)
    raise FprgSyntaxError(f"{what} '{text}' must be a variable or an array element")


class Stmt:
    __slots__ = ("path",)


class Declare(Stmt):
    __slots__ = ("names", "type", "is_array", "size")


class Assign(Stmt):
    __slots__ = ("target", "expr")


class Input(Stmt):
    __slots__ = ("target",)


class Output(Stmt):
    __slots__ = ("expr", "newline")


class If(Stmt):
    __slots__ = ("cond", "then", "else_")


class While(Stmt):
    __slots__ = ("cond", "body")


class Do(Stmt):
    __slots__ = ("cond", "body")


class For(Stmt):
    __slots__ = ("var", "start", "end", "step", "dec", "body")


class CallStmt(Stmt):
    __slots__ = ("call",)


class Param:
    __slots__ = ("name", "lower", "type", "is_array")

    def __init__(self, name: str, ptype: str, is_array: bool):
        self.name, self.lower, self.type, self.is_array = name, name.lower(), ptype, is_array


class Function:
    __slots__ = ("name", "lower", "type", "return_var", "params", "body", "path")

    def __init__(self, name: str, ftype: str, return_var: str, params: list, body: list, path: str):
        self.name, self.lower, self.type = name, name.lower(), ftype
        self.return_var, self.params, self.body, self.path = return_var, params, body, path


class Program:
    """The functions of one .fprg file, keyed by lower-cased name."""

    def __init__(self, functions: dict, attributes: dict):
        self.functions = functions
        self.attributes = attributes

    @property
    def main(self) -> Function:
        return self.functions["main"]


def _attr_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def load_program(xml_text: Union[str, bytes]) -> Program:
    """Parse the XML of a .fprg file into a Program; raises FprgSyntaxError on bad files."""
    try:
        try:
            root = ET.fromstring(xml_text)
        except ValueError:
            # a str with an encoding declaration: let the XML parser decode the bytes itself
            root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        raise FprgSyntaxError(f"not a well-formed .fprg file: {e}") from None
    if root.tag != "flowgorithm":
        raise FprgSyntaxError(f"not a .fprg file: root element is <{root.tag}>, expected <flowgorithm>")
    attributes = {}
    attrs_el = root.find("attributes")
    if attrs_el is not None:
        for a in attrs_el.findall("attribute"):
            attributes.setdefault(a.get("name", ""), a.get("value", ""))
    functions: dict = {}
    for idx, el in enumerate(root.findall("function")):
        fn = _load_function(el, idx)
        if fn.lower in functions:
            raise FprgSyntaxError(f"function '{fn.name}' is defined twice", function=fn.name, path=fn.path)
        functions[fn.lower] = fn
    if "main" not in functions:
        raise FprgSyntaxError("the file has no Main function")
    return Program(functions, attributes)


def _load_function(el: ET.Element, idx: int) -> Function:
    name = el.get("name")
    if not name:
        raise FprgSyntaxError(f"function #{idx + 1} has no name", path=f"function[{idx}]")
    ftype = el.get("type", "None")
    if ftype not in ("None",) + VALUE_TYPES:
        raise FprgSyntaxError(f"function type '{ftype}' is not None, Integer, Real, String or Boolean",
                              function=name, path=name)
    params = []
    params_el = el.find("parameters")
    if params_el is not None:
        for p in params_el.findall("parameter"):
            pname = p.get("name", "")
            ptype = p.get("type", "")
            if not pname or ptype not in VALUE_TYPES:
                raise FprgSyntaxError(f"bad parameter name='{pname}' type='{ptype}'", function=name,
                                      path=f"{name}/parameters")
            params.append(Param(pname, ptype, _attr_bool(p.get("array"), False)))
    body_el = el.find("body")
    body = _load_block(body_el, f"{name}/body", name) if body_el is not None else []
    return Function(name, ftype, el.get("variable", "") or "", params, body, name)


def _require(el: ET.Element, attr: str, path: str, fname: str) -> str:
    value = el.get(attr)
    if value is None:
        raise FprgSyntaxError(f"<{el.tag}> is missing the '{attr}' attribute", function=fname, path=path)
    return value


def _load_block(container: ET.Element, path: str, fname: str) -> list:
    stmts = []
    for i, el in enumerate(container):
        spath = f"{path}[{i}]/{el.tag}"
        try:
            st = _load_statement(el, spath, fname)
        except FprgSyntaxError as e:
            raise e.located(fname, spath)
        if st is not None:
            st.path = spath
            stmts.append(st)
    return stmts


def _load_statement(el: ET.Element, spath: str, fname: str) -> Optional[Stmt]:
    tag = el.tag
    if tag == "declare":
        names_attr = el.get("name")
        if names_attr is None:
            names_attr = el.get("variables")  # Flowgorithm 1.x
        if names_attr is None:
            raise FprgSyntaxError("<declare> has neither 'name' nor 'variables'")
        st = Declare()
        st.names = []
        for raw in names_attr.split(","):
            n = raw.strip()
            if not n:
                raise FprgSyntaxError(f"empty name in declare list '{names_attr}'")
            st.names.append((n, n.lower()))
        st.type = _require(el, "type", spath, fname)
        if st.type not in VALUE_TYPES:
            raise FprgSyntaxError(f"declared type '{st.type}' is not Integer, Real, String or Boolean")
        st.is_array = _attr_bool(el.get("array"), False)
        size = el.get("size", "")
        if st.is_array:
            if not size.strip():
                raise FprgSyntaxError("array declaration without a size expression")
            st.size = parse_expression(size)
        else:
            st.size = None
        return st
    if tag == "assign":
        st = Assign()
        st.target = parse_target(_require(el, "variable", spath, fname), "assignment target")
        st.expr = parse_expression(_require(el, "expression", spath, fname))
        return st
    if tag == "input":
        st = Input()
        st.target = parse_target(_require(el, "variable", spath, fname), "input target")
        return st
    if tag == "output":
        st = Output()
        st.expr = parse_expression(_require(el, "expression", spath, fname))
        st.newline = _attr_bool(el.get("newline"), True)
        return st
    if tag == "if":
        st = If()
        st.cond = parse_expression(_require(el, "expression", spath, fname))
        then_el = el.find("then")
        else_el = el.find("else")
        st.then = _load_block(then_el, f"{spath}/then", fname) if then_el is not None else []
        st.else_ = _load_block(else_el, f"{spath}/else", fname) if else_el is not None else []
        return st
    if tag == "while" or tag == "do":
        st = While() if tag == "while" else Do()
        st.cond = parse_expression(_require(el, "expression", spath, fname))
        st.body = _load_block(el, spath, fname)
        return st
    if tag == "for":
        st = For()
        var = parse_target(_require(el, "variable", spath, fname), "loop variable")
        if var.index is not None:
            raise FprgSyntaxError(f"loop variable '{var.text}' must be a plain variable")
        st.var = var
        st.start = parse_expression(_require(el, "start", spath, fname))
        st.end = parse_expression(_require(el, "end", spath, fname))
        st.step = parse_expression(el.get("step") or "1")
        direction = (el.get("direction") or "inc").strip().lower()
        if direction not in ("inc", "dec"):
            raise FprgSyntaxError(f"for direction '{direction}' is neither inc nor dec")
        st.dec = direction == "dec"
        st.body = _load_block(el, spath, fname)
        return st
    if tag == "call":
        st = CallStmt()
        node = parse_expression(_require(el, "expression", spath, fname))
        if node[0] != "call":
            raise FprgSyntaxError(f"<call> expression '{el.get('expression')}' is not a function call")
        st.call = node
        return st
    if tag in ("comment", "breakpoint"):
        return None
    raise FprgSyntaxError(f"unsupported statement <{tag}>")


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

class Slot:
    """One variable of a frame."""
    __slots__ = ("name", "type", "is_array", "value")

    def __init__(self, name: str, vtype: str, is_array: bool, value):
        self.name, self.type, self.is_array, self.value = name, vtype, is_array, value


class Frame:
    __slots__ = ("fn", "vars")

    def __init__(self, fn: Function):
        self.fn = fn
        self.vars: dict = {}


INTRINSIC_ARITY = {
    "abs": 1, "arcsin": 1, "arccos": 1, "arctan": 1, "cos": 1, "int": 1, "ln": 1, "log": 1,
    "log10": 1, "sgn": 1, "sin": 1, "sqrt": 1, "tan": 1,
    "len": 1, "char": 2,
    "tochar": 1, "tocode": 1, "tofixed": 2, "tointeger": 1, "toreal": 1, "tostring": 1,
    "eof": 0, "random": 1, "size": 1,
}
INTRINSIC_NAMES = {
    "abs": "Abs", "arcsin": "Arcsin", "arccos": "Arccos", "arctan": "Arctan", "cos": "Cos", "int": "Int",
    "ln": "Ln", "log": "Log", "log10": "Log10", "sgn": "Sgn", "sin": "Sin", "sqrt": "Sqrt", "tan": "Tan",
    "len": "Len", "char": "Char", "tochar": "ToChar", "tocode": "ToCode", "tofixed": "ToFixed",
    "tointeger": "ToInteger", "toreal": "ToReal", "tostring": "ToString", "eof": "EOF",
    "random": "Random", "size": "Size",
}

_EMPTY_PROGRAM_XML = ('<flowgorithm fileversion="3.0"><function name="Main" type="None" variable="">'
                      '<parameters/><body/></function></flowgorithm>')


class Machine:
    """Runs one program. After ``run()``: ``output`` (str), ``variables`` (Main's final variables,
    declared spelling -> value, arrays as lists), ``steps`` (statements executed).

    ``inputs`` is a sequence (or any iterable, e.g. a lazy stdin reader) of input lines.
    ``random_values`` fixes ``Random(n)`` to ``next(random_values) % n``; otherwise ``seed`` seeds
    a private ``random.Random``. ``echo`` is a text stream that receives the output as it is produced.
    """

    def __init__(self, program: Union[Program, str, bytes], inputs: Iterable[str] = (), *,
                 random_values: Optional[Iterable[int]] = None, seed: Optional[int] = None,
                 max_steps: int = 1_000_000, max_depth: int = 1000, echo=None):
        self.program = program if isinstance(program, Program) else load_program(program)
        if isinstance(inputs, str):
            inputs = inputs.splitlines()
        self._inputs: Iterator[str] = iter(inputs)
        self._randoms: Optional[Iterator[int]] = iter(random_values) if random_values is not None else None
        self._rng = _random.Random(seed)
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.echo = echo
        self._chunks: list = []
        self.steps = 0
        self.depth = 0
        self.variables: dict = {}
        self.inputs_consumed = 0
        self._exec_table: dict = {
            Declare: self._x_declare, Assign: self._x_assign, Input: self._x_input, Output: self._x_output,
            If: self._x_if, While: self._x_while, Do: self._x_do, For: self._x_for, CallStmt: self._x_call,
        }

    # -- public --------------------------------------------------------------
    @property
    def output(self) -> str:
        return "".join(self._chunks)

    def run(self) -> str:
        """Execute Main; returns the console output (also in ``self.output``)."""
        main = self.program.main
        frame = Frame(main)
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, 60 * self.max_depth + 2000))
        try:
            try:
                self._exec_block(main.body, frame)
            except RecursionError:
                raise FprgRuntimeError("the program recursed too deeply") from None
        finally:
            sys.setrecursionlimit(old_limit)
            self.variables = {slot.name: slot.value for slot in frame.vars.values()}
        return self.output

    def evaluate(self, text: str, variables: Optional[dict] = None):
        """Evaluate a standalone expression with the given variable bindings (Python values)."""
        frame = Frame(self.program.main)
        for name, value in (variables or {}).items():
            if isinstance(value, list) and not isinstance(value, FArray):
                etype = type_name(value[0]) if value else INTEGER
                value = FArray(value, etype)
            if isinstance(value, FArray):
                frame.vars[name.lower()] = Slot(name, value.etype, True, value)
            else:
                frame.vars[name.lower()] = Slot(name, type_name(value), False, value)
        return self._eval(parse_expression(text), frame)

    # -- statements ------------------------------------------------------------
    def _tick(self, frame: Frame, path: str) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise FprgRuntimeError(f"more than {self.max_steps} statements executed (infinite loop?); "
                                   f"raise max_steps if the program really needs more",
                                   function=frame.fn.name, path=path)

    def _exec_block(self, stmts: list, frame: Frame) -> None:
        for st in stmts:
            self._tick(frame, st.path)
            try:
                self._exec_table[type(st)](st, frame)
            except FprgRuntimeError as e:
                raise e.located(frame.fn.name, st.path)

    def _x_declare(self, st: Declare, frame: Frame) -> None:
        for name, lower in st.names:
            if st.is_array:
                n = self._eval(st.size, frame)
                if type(n) is not int:
                    raise FprgRuntimeError(f"array size of '{name}' must be an Integer, got {_describe(n)}")
                if n < 0:
                    raise FprgRuntimeError(f"array size of '{name}' is negative ({n})")
                value = FArray([DEFAULTS[st.type]] * n, st.type)
            else:
                value = DEFAULTS[st.type]
            frame.vars[lower] = Slot(name, st.type, st.is_array, value)

    def _x_assign(self, st: Assign, frame: Frame) -> None:
        self._store(st.target, self._eval(st.expr, frame), frame)

    def _x_input(self, st: Input, frame: Frame) -> None:
        slot = self._slot(st.target.lower, st.target.name, frame)
        what = f"variable '{st.target.text}'"
        if st.target.index is None:
            if slot.is_array:
                raise FprgRuntimeError(f"'{st.target.name}' is an array; input into an element "
                                       f"'{st.target.name}[i]'")
            vtype = slot.type
        else:
            if not slot.is_array:
                raise FprgRuntimeError(f"'{st.target.name}' is not an array and cannot be indexed")
            vtype = slot.value.etype
        try:
            text = next(self._inputs)
        except StopIteration:
            raise FprgRuntimeError(f"the program asked for input into '{st.target.text}' but no input is left "
                                   f"({self.inputs_consumed} line(s) were consumed)") from None
        self.inputs_consumed += 1
        if not isinstance(text, str):
            text = str(text)
        self._store(st.target, convert_input(text, vtype, what), frame, slot)

    def _x_output(self, st: Output, frame: Frame) -> None:
        text = format_value(self._eval(st.expr, frame))
        if st.newline:
            text += "\n"
        self._chunks.append(text)
        if self.echo is not None:
            self.echo.write(text)
            self.echo.flush()

    def _condition(self, node: Node, frame: Frame, what: str) -> bool:
        value = self._eval(node, frame)
        if type(value) is not bool:
            raise FprgRuntimeError(f"the {what} condition must be Boolean, got {_describe(value)}")
        return value

    def _x_if(self, st: If, frame: Frame) -> None:
        if self._condition(st.cond, frame, "if"):
            self._exec_block(st.then, frame)
        else:
            self._exec_block(st.else_, frame)

    def _x_while(self, st: While, frame: Frame) -> None:
        while self._condition(st.cond, frame, "while"):
            self._exec_block(st.body, frame)
            self._tick(frame, st.path)

    def _x_do(self, st: Do, frame: Frame) -> None:
        while True:
            self._exec_block(st.body, frame)
            self._tick(frame, st.path)
            if not self._condition(st.cond, frame, "do"):
                break

    def _x_for(self, st: For, frame: Frame) -> None:
        slot = self._slot(st.var.lower, st.var.name, frame)
        if slot.is_array or slot.type not in (INTEGER, REAL):
            raise FprgRuntimeError(f"loop variable '{st.var.name}' must be an Integer or Real variable, "
                                   f"it is {'an array' if slot.is_array else slot.type}")
        start = self._eval(st.start, frame)
        end = self._eval(st.end, frame)
        step = self._eval(st.step, frame)
        for label, v in (("start", start), ("end", end), ("step", step)):
            if not _is_number(v):
                raise FprgRuntimeError(f"for-loop {label} must be a number, got {_describe(v)}")
        if step <= 0:
            raise FprgRuntimeError(f"for-loop step must be positive, got {format_value(step)}")
        what = f"loop variable '{st.var.name}'"
        slot.value = coerce(start, slot.type, what)
        while True:
            self._tick(frame, st.path)
            current = slot.value
            if (current < end) if st.dec else (current > end):
                break
            self._exec_block(st.body, frame)
            slot.value = coerce(slot.value - step if st.dec else slot.value + step, slot.type, what)

    def _x_call(self, st: CallStmt, frame: Frame) -> None:
        self._call(st.call, frame, as_statement=True)

    # -- variables -------------------------------------------------------------
    def _slot(self, lower: str, name: str, frame: Frame) -> Slot:
        slot = frame.vars.get(lower)
        if slot is None:
            raise FprgRuntimeError(f"variable '{name}' is not declared in function {frame.fn.name}")
        return slot

    def _element_index(self, slot: Slot, name: str, index_node: Node, frame: Frame) -> int:
        if not slot.is_array:
            raise FprgRuntimeError(f"'{name}' is not an array and cannot be indexed")
        idx = self._eval(index_node, frame)
        if type(idx) is not int:
            raise FprgRuntimeError(f"index of '{name}' must be an Integer, got {_describe(idx)}")
        if not 0 <= idx < len(slot.value):
            raise FprgRuntimeError(f"index {idx} is out of range for '{name}' (size {len(slot.value)})")
        return idx

    def _store(self, target: Target, value, frame: Frame, slot: Optional[Slot] = None) -> None:
        if slot is None:
            slot = self._slot(target.lower, target.name, frame)
        if target.index is None:
            if slot.is_array:
                raise FprgRuntimeError(f"'{target.name}' is an array; assign to an element '{target.name}[i]'")
            slot.value = coerce(value, slot.type, f"variable '{target.name}'")
        else:
            idx = self._element_index(slot, target.name, target.index, frame)
            arr = slot.value
            arr[idx] = coerce(value, arr.etype, f"element '{target.name}[{idx}]'")

    # -- expressions -----------------------------------------------------------
    def _eval(self, node: Node, frame: Frame):
        tag = node[0]
        if tag == "num" or tag == "str" or tag == "bool":
            return node[1]
        if tag == "var":
            return self._slot(node[2], node[1], frame).value
        if tag == "bin":
            return self._binary(node[1], self._eval(node[2], frame), self._eval(node[3], frame))
        if tag == "call":
            return self._call(node, frame, as_statement=False)
        if tag == "index":
            slot = self._slot(node[2], node[1], frame)
            return slot.value[self._element_index(slot, node[1], node[3], frame)]
        if tag == "neg":
            v = self._eval(node[1], frame)
            if not _is_number(v):
                raise FprgRuntimeError(f"unary '-' needs a number, got {_describe(v)}")
            return -v
        if tag == "not":
            v = self._eval(node[1], frame)
            if type(v) is not bool:
                raise FprgRuntimeError(f"'not' needs a Boolean, got {_describe(v)}")
            return not v
        if tag == "and" or tag == "or":
            left = self._eval(node[1], frame)
            if type(left) is not bool:
                raise FprgRuntimeError(f"left operand of '{tag}' must be Boolean, got {_describe(left)}")
            if left is (tag == "or"):   # short circuit: false and ..., true or ...
                return left
            right = self._eval(node[2], frame)
            if type(right) is not bool:
                raise FprgRuntimeError(f"right operand of '{tag}' must be Boolean, got {_describe(right)}")
            return right
        if tag == "pi":
            return math.pi
        raise FprgRuntimeError(f"internal error: unknown expression node {tag!r}")

    def _binary(self, op: str, a, b):
        if op == "&":
            return format_value(a) + format_value(b)
        if op in ("==", "!=", "<", ">", "<=", ">="):
            ta, tb = type(a), type(b)
            if (ta is int or ta is float) and (tb is int or tb is float):
                pass
            elif ta is str and tb is str:
                pass
            elif ta is bool and tb is bool and op in ("==", "!="):
                pass
            else:
                raise FprgRuntimeError(f"cannot compare {_describe(a)} with {_describe(b)} using '{op}'")
            if op == "==":
                return a == b
            if op == "!=":
                return a != b
            if op == "<":
                return a < b
            if op == ">":
                return a > b
            if op == "<=":
                return a <= b
            return a >= b
        # arithmetic
        if not (_is_number(a) and _is_number(b)):
            hint = "; use '&' to join text" if op == "+" and (type(a) is str or type(b) is str) else ""
            raise FprgRuntimeError(f"operator '{op}' needs numbers, got {_describe(a)} and {_describe(b)}{hint}")
        if op == "^":
            return self._power(a, b)
        if op in ("/", "%") and b == 0:
            raise FprgRuntimeError(f"division by zero in '{op}'")
        try:
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return a / b
            if op == "%":
                if type(a) is int and type(b) is int:
                    r = abs(a) % abs(b)
                    return -r if a < 0 else r
                return math.fmod(a, b)
        except OverflowError:
            raise FprgRuntimeError(f"overflow in '{op}' ({format_value(a)} {op} {format_value(b)})") from None
        raise FprgRuntimeError(f"internal error: unknown operator {op!r}")

    @staticmethod
    def _power(a, b):
        if type(a) is int and type(b) is int and b >= 0:
            if b > 100_000 and abs(a) > 1:
                raise FprgRuntimeError(f"'^' exponent {b} is too large")
            return a ** b
        try:
            r = float(a) ** float(b)
        except OverflowError:
            raise FprgRuntimeError("overflow in '^'") from None
        except ZeroDivisionError:
            raise FprgRuntimeError("0 raised to a negative power") from None
        if isinstance(r, complex):
            raise FprgRuntimeError(f"'^' of a negative base {format_value(a)} with a fractional exponent "
                                   f"{format_value(b)} has no real value")
        return r

    # -- calls -----------------------------------------------------------------
    def _call(self, node: Node, frame: Frame, *, as_statement: bool):
        name, lower, arg_nodes = node[1], node[2], node[3]
        arity = INTRINSIC_ARITY.get(lower)
        if arity is not None:
            if len(arg_nodes) != arity:
                raise FprgRuntimeError(f"{INTRINSIC_NAMES[lower]}() takes {arity} argument(s), "
                                       f"{len(arg_nodes)} given")
            args = [self._eval(a, frame) for a in arg_nodes]
            return self._intrinsic(lower, args)
        fn = self.program.functions.get(lower)
        if fn is None:
            raise FprgRuntimeError(f"unknown function '{name}'")
        if fn.type == "None" and not as_statement:
            raise FprgRuntimeError(f"function '{fn.name}' returns no value and cannot be used in an expression")
        if len(arg_nodes) != len(fn.params):
            raise FprgRuntimeError(f"function '{fn.name}' takes {len(fn.params)} argument(s), "
                                   f"{len(arg_nodes)} given")
        new = Frame(fn)
        for p, anode in zip(fn.params, arg_nodes):
            value = self._eval(anode, frame)
            what = f"parameter '{p.name}' of {fn.name}"
            if p.is_array:
                if not isinstance(value, FArray):
                    raise FprgRuntimeError(f"{what} is a {p.type} array, got {_describe(value)}")
                if value.etype != p.type:
                    raise FprgRuntimeError(f"{what} is a {p.type} array, got a {value.etype} array")
                new.vars[p.lower] = Slot(p.name, p.type, True, value)   # by reference
            else:
                if isinstance(value, FArray):
                    raise FprgRuntimeError(f"{what} is a {p.type}, got {_describe(value)}")
                new.vars[p.lower] = Slot(p.name, p.type, False, coerce(value, p.type, what))
        self.depth += 1
        if self.depth > self.max_depth:
            raise FprgRuntimeError(f"call depth exceeded {self.max_depth} (runaway recursion in '{fn.name}'?)")
        try:
            self._exec_block(fn.body, new)
        finally:
            self.depth -= 1
        if fn.type == "None":
            return None
        slot = new.vars.get(fn.return_var.lower())
        if slot is None:
            raise FprgRuntimeError(f"function '{fn.name}' ended without declaring its return variable "
                                   f"'{fn.return_var}'", function=fn.name, path=fn.path)
        if slot.is_array:
            raise FprgRuntimeError(f"return variable '{fn.return_var}' of '{fn.name}' is an array",
                                   function=fn.name, path=fn.path)
        return coerce(slot.value, fn.type, f"the {fn.type} result of '{fn.name}'")

    def _intrinsic(self, lower: str, args: list):
        disp = INTRINSIC_NAMES[lower]

        def num(i: int):
            v = args[i]
            if not _is_number(v):
                raise FprgRuntimeError(f"{disp}() needs a number, got {_describe(v)}")
            return v

        def integer(i: int):
            v = args[i]
            if type(v) is not int:
                raise FprgRuntimeError(f"{disp}() needs an Integer, got {_describe(v)}")
            return v

        def string(i: int):
            v = args[i]
            if type(v) is not str:
                raise FprgRuntimeError(f"{disp}() needs a String, got {_describe(v)}")
            return v

        try:
            if lower == "abs":
                return abs(num(0))
            if lower == "sgn":
                v = num(0)
                return (v > 0) - (v < 0)
            if lower == "int":
                v = num(0)
                if type(v) is float and (v != v or v in (math.inf, -math.inf)):
                    raise FprgRuntimeError(f"Int() of {format_value(v)}")
                return int(v)
            if lower == "sqrt":
                v = num(0)
                if v < 0:
                    raise FprgRuntimeError(f"Sqrt() of a negative number ({format_value(v)})")
                return math.sqrt(v)
            if lower in ("sin", "cos", "tan"):
                return getattr(math, lower)(num(0))
            if lower in ("arcsin", "arccos"):
                v = num(0)
                if not -1 <= v <= 1:
                    raise FprgRuntimeError(f"{disp}() argument {format_value(v)} is outside -1..1")
                return math.asin(v) if lower == "arcsin" else math.acos(v)
            if lower == "arctan":
                return math.atan(num(0))
            if lower in ("ln", "log", "log10"):
                v = num(0)
                if v <= 0:
                    raise FprgRuntimeError(f"{disp}() of a non-positive number ({format_value(v)})")
                return math.log10(v) if lower == "log10" else math.log(v)
            if lower == "len":
                return len(string(0))
            if lower == "char":
                s = string(0)
                i = integer(1)
                if not 0 <= i < len(s):
                    raise FprgRuntimeError(f"Char() index {i} is out of range for a string of length {len(s)}")
                return s[i]
            if lower == "tochar":
                code = integer(0)
                if not 0 <= code <= 0x10FFFF:
                    raise FprgRuntimeError(f"ToChar() code {code} is not a valid character code")
                return chr(code)
            if lower == "tocode":
                s = string(0)
                if not s:
                    raise FprgRuntimeError("ToCode() of an empty string")
                return ord(s[0])
            if lower == "tofixed":
                v = num(0)
                digits = integer(1)
                if digits < 0:
                    raise FprgRuntimeError(f"ToFixed() needs a non-negative number of decimals, got {digits}")
                return f"{float(v):.{digits}f}"
            if lower == "tointeger":
                v = args[0]
                if type(v) is int:
                    return v
                if type(v) is float:
                    return coerce(v, INTEGER, "ToInteger()")
                if type(v) is str:
                    if _INT_TEXT.fullmatch(v.strip()):
                        return int(v.strip())
                    raise FprgRuntimeError(f"ToInteger() cannot convert {v!r}")
                raise FprgRuntimeError(f"ToInteger() cannot convert {_describe(v)}")
            if lower == "toreal":
                v = args[0]
                if _is_number(v):
                    return float(v)
                if type(v) is str:
                    try:
                        return float(v.strip())
                    except ValueError:
                        raise FprgRuntimeError(f"ToReal() cannot convert {v!r}") from None
                raise FprgRuntimeError(f"ToReal() cannot convert {_describe(v)}")
            if lower == "tostring":
                return format_value(args[0])
            if lower == "eof":
                return True
            if lower == "random":
                n = integer(0)
                if n <= 0:
                    raise FprgRuntimeError(f"Random() needs a positive Integer, got {n}")
                if self._randoms is not None:
                    try:
                        v = next(self._randoms)
                    except StopIteration:
                        raise FprgRuntimeError("Random(): the scripted random_values sequence is exhausted") from None
                    if type(v) is not int:
                        raise FprgRuntimeError(f"random_values must be integers, got {v!r}")
                    return v % n
                return self._rng.randrange(n)
            if lower == "size":
                v = args[0]
                if not isinstance(v, FArray):
                    raise FprgRuntimeError(f"Size() needs an array, got {_describe(v)}")
                return len(v)
        except (ValueError, OverflowError) as e:
            raise FprgRuntimeError(f"{disp}(): {e}") from None
        raise FprgRuntimeError(f"internal error: intrinsic {disp} not implemented")


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------

def run_string(xml_text: Union[str, bytes], inputs: Iterable[str] = (), *,
               random_values: Optional[Iterable[int]] = None, seed: Optional[int] = None,
               max_steps: int = 1_000_000, **kw) -> str:
    """Run the .fprg XML given as text with scripted inputs; returns the complete console output."""
    return Machine(xml_text, inputs, random_values=random_values, seed=seed, max_steps=max_steps, **kw).run()


def run_file(path: str, inputs: Iterable[str] = (), **kw) -> str:
    """Run a .fprg file with scripted inputs; returns the complete console output."""
    with open(path, "rb") as f:
        return run_string(f.read(), inputs, **kw)


def evaluate(text: str, variables: Optional[dict] = None, *, random_values: Optional[Iterable[int]] = None,
             seed: Optional[int] = None):
    """Evaluate one Flowgorithm expression (no program needed), e.g. ``evaluate("1 + 3 ^ 2") == 10``.

    ``variables`` binds names to Python values (bool/int/float/str, or a list for an array).
    """
    m = Machine(_EMPTY_PROGRAM_XML, (), random_values=random_values, seed=seed)
    return m.evaluate(text, variables)


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _stdin_lines() -> Iterator[str]:
    for line in sys.stdin:
        yield line.rstrip("\r\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="fprg_run", description="Run a Flowgorithm .fprg flowchart headlessly.",
                                 epilog="Input lines come from --input (repeatable), --input-file, or stdin.")
    ap.add_argument("file", help="the .fprg file to run")
    ap.add_argument("--input", "-i", action="append", metavar="LINE", help="one line of input (repeatable)")
    ap.add_argument("--input-file", metavar="PATH", help="file with one input line per line")
    ap.add_argument("--random", metavar="N,N,...", help="fixed values for Random(n), used as value %% n in order")
    ap.add_argument("--seed", type=int, metavar="N", help="seed for Random() when --random is not given")
    ap.add_argument("--max-steps", type=int, default=1_000_000, metavar="N",
                    help="stop after N statements (default 1000000)")
    ap.add_argument("--vars", action="store_true", help="print Main's variables after the run")
    args = ap.parse_args(argv)

    inputs: Iterable[str]
    if args.input is not None:
        inputs = args.input
    elif args.input_file is not None:
        try:
            with open(args.input_file, encoding="utf-8") as f:
                inputs = [line.rstrip("\r\n") for line in f]
        except OSError as e:
            print(f"fprg_run: cannot read input file: {e}", file=sys.stderr)
            return 1
    else:
        inputs = _stdin_lines()
    random_values = None
    if args.random is not None:
        try:
            random_values = [int(v) for v in args.random.split(",") if v.strip() != ""]
        except ValueError:
            print(f"fprg_run: --random needs comma-separated integers, got {args.random!r}", file=sys.stderr)
            return 1
    try:
        with open(args.file, "rb") as f:
            xml_text = f.read()
    except OSError as e:
        print(f"fprg_run: cannot read {args.file}: {e}", file=sys.stderr)
        return 1
    machine = None
    try:
        machine = Machine(xml_text, inputs, random_values=random_values, seed=args.seed,
                          max_steps=args.max_steps, echo=sys.stdout)
        machine.run()
    except FprgRuntimeError as e:
        try:
            sys.stdout.flush()
            if machine is not None and machine.output and not machine.output.endswith("\n"):
                print()
        except BrokenPipeError:
            pass
        print(f"fprg_run: error: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        # the reader went away (e.g. `| head`): leave quietly without a traceback
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    if args.vars:
        if machine.output and not machine.output.endswith("\n"):
            print()
        print("--- variables of Main ---")
        for name, value in machine.variables.items():
            shown = f"[{', '.join(format_value(v) for v in value)}]" if isinstance(value, FArray) \
                else format_value(value)
            print(f"{name} = {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
