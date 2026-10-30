"""Convert the functions of a Flowgorithm-dialect Python program into Flowgorithm shapes.

The dialect is Python that maps one to one onto Flowgorithm (README: "The dialect"): typed
functions, Output/Input and the intrinsic functions from the `flowgorithm` library, if/while/for,
the `while True: ... if cond: break` Do loop, arrays made with `[0] * n`. Anything else is a
ConvertError that says what to write instead.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple, Optional

from .layout import find_else_line, header_end, indent_of, parse_directive, trailing_end
from .model import (ArrayT, Assign, BOOLEAN, Breakpoint, Call, Comment, ConvertError, Declare, Do, FgType,
                    For, Function, INTEGER, If, Input, Namespace, Output, P_ADD, P_AND, P_ATOM, P_CAT,
                    P_OR, P_POW, P_REL, P_UNARY, Param, REAL, STRING, VOID, Warning_, While, is_numeric,
                    legalize, type_name, P_MUL)

if TYPE_CHECKING:  # pragma: no cover
    from .program import FuncInfo, ProgramBuilder

PY_TYPES = {"int": INTEGER, "float": REAL, "str": STRING, "bool": BOOLEAN}
COMPARE_OP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
FLIP_COMPARE = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.LtE: ast.Gt, ast.Gt: ast.LtE,
                ast.GtE: ast.Lt}
DEFAULT_FILL = {INTEGER: 0, REAL: 0.0, STRING: "", BOOLEAN: False}
OPERATORS = {ast.Add: ("+", P_ADD), ast.Sub: ("-", P_ADD), ast.Mult: ("*", P_MUL), ast.Div: ("/", P_MUL),
             ast.Mod: ("%", P_MUL), ast.Pow: ("^", P_POW)}

NUM, ANY, ARRAY = "number", "any", "array"
# The library's intrinsic functions: argument kinds, result type (None: the type of the argument).
LIBRARY = {
    "Abs": ([NUM], None), "Sgn": ([NUM], INTEGER), "Int": ([NUM], INTEGER), "Sqrt": ([NUM], REAL),
    "Sin": ([NUM], REAL), "Cos": ([NUM], REAL), "Tan": ([NUM], REAL), "Arcsin": ([NUM], REAL),
    "Arccos": ([NUM], REAL), "Arctan": ([NUM], REAL), "Ln": ([NUM], REAL), "Log": ([NUM], REAL),
    "Log10": ([NUM], REAL), "Len": ([STRING], INTEGER), "Char": ([STRING, INTEGER], STRING),
    "ToChar": ([INTEGER], STRING), "ToCode": ([STRING], INTEGER), "ToFixed": ([NUM, INTEGER], STRING),
    "ToInteger": ([STRING], INTEGER), "ToReal": ([STRING], REAL), "ToString": ([NUM], STRING),
    "Random": ([INTEGER], INTEGER), "Size": ([ARRAY], INTEGER),
}
CUT = "cut the fraction off with Int(...)"
STATEMENT_HINTS = {
    "import": "the flowgorithm library has the math functions (Sqrt, Abs, Sin, ..., pi) and Random(n)",
    "global": "pass values in as parameters and give results back with return",
    "nonlocal": "pass values in as parameters and give results back with return",
    "try": "check the value with an if before using it", "raise": "Output a message instead",
    "assert": "check with an if and Output a message", "del": "a variable cannot be removed",
    "with": "Flowgorithm has no files or resources to open", "class": "Flowgorithm has functions only",
    "match": "use if / elif / else",
}
# What to write when a library function gets the wrong kind of value.
ARG_HINTS = {
    "ToInteger": "ToInteger() reads a whole number from text; Int(x) cuts off the fraction of a number",
    "ToReal": "ToReal() reads a number from text; a number goes into a Real variable as it is (x: float = n)",
    "ToString": "ToString() turns a number into text; Output(...) shows Booleans and Strings as they are",
}
# What to write instead of Python that is not part of the dialect.
INSTEAD = {
    "print": "use Output(...)", "input": "use Input(int), Input(float), Input(str) or Input(bool)",
    "len": "use Len(text) for a String or Size(array) for an array",
    "int": "use ToInteger(text), or Int(number) to cut off the fraction", "float": "use ToReal(...)",
    "str": "use ToString(...)", "abs": "use Abs(...)", "round": "use ToFixed(x, digits) or Int(x + 0.5)",
    "ord": "use ToCode(...)", "chr": "use ToChar(...)", "range": "range() belongs in a for loop header",
    "min": "compare with an if statement", "max": "compare with an if statement",
    "sum": "add the elements up in a loop", "pow": "use the ** operator",
}


class Ex(NamedTuple):
    """A converted expression: Flowgorithm text, its precedence, its type."""
    text: str
    prec: int
    type: FgType


@dataclass
class VarInfo:
    py: str
    fg: str
    type: FgType
    order: int
    is_param: bool = False
    is_const: bool = False
    const_text: str = ""
    declared: bool = False  # annotated: the type is fixed


def paren(e: Ex, prec: int, side: str = "left") -> str:
    """An operand's text, parenthesised when it binds less tightly than its context needs."""
    if e.prec < prec or (e.prec == prec and (side == "right" or prec == P_POW)):
        return f"({e.text})"
    return e.text


def string_literal(s: str) -> Ex:
    """A Flowgorithm string literal; double quotes and control characters go through ToChar()."""
    parts: list[str] = []
    buf = ""
    for ch in s:
        if ch == '"' or ord(ch) < 32:
            if buf:
                parts.append(f'"{buf}"')
                buf = ""
            parts.append(f"ToChar({ord(ch)})")
        else:
            buf += ch
    if buf or not parts:
        parts.append(f'"{buf}"')
    return Ex(" & ".join(parts), P_CAT if len(parts) > 1 else P_ATOM, STRING)


def float_text(v: float) -> str:
    """Flowgorithm has no exponent notation: plain decimals only."""
    s = repr(v)
    if "e" in s or "inf" in s or "nan" in s:
        raise ValueError(f"the number {v!r} has no plain decimal form; write it out or compute it "
                         "(for example 10 ^ -5)")
    return s


def literal_text(value) -> str:
    """Flowgorithm text of a literal value (a constant's value)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return float_text(value)
    if isinstance(value, str):
        return string_literal(value).text
    return str(value)


def literal_value(node: ast.AST):
    """Python value of a literal (also a negated number); ValueError for anything else."""
    if isinstance(node, ast.Constant) and type(node.value) in (bool, int, float, str):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float)):
        return -node.operand.value
    raise ValueError("not a literal")


def value_type(value) -> str:
    return {bool: BOOLEAN, int: INTEGER, float: REAL, str: STRING}[type(value)]


def py_name(t: FgType) -> str:
    return {INTEGER: "int", REAL: "float", STRING: "str", BOOLEAN: "bool"}.get(t, str(t))


def annotation_type(ann: ast.expr, allow_none: bool = False) -> FgType:
    """int / float / str / bool / list[...] (and None for a return annotation)."""
    if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        try:
            ann = ast.parse(ann.value.strip(), mode="eval").body
        except SyntaxError:
            raise ValueError(f"invalid type annotation {ann.value!r}") from None
    if allow_none and isinstance(ann, ast.Constant) and ann.value is None:
        return VOID
    if isinstance(ann, ast.Name) and ann.id in PY_TYPES:
        return PY_TYPES[ann.id]
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id == "list":
        inner = annotation_type(ann.slice)
        if isinstance(inner, ArrayT):
            raise ValueError("arrays of arrays are not supported (Flowgorithm arrays are 1-D)")
        return ArrayT(inner)
    raise ValueError(f"unsupported type annotation '{ast.unparse(ann)}' (use int, float, str, bool or list[...])")


def is_break_if(s: ast.stmt) -> bool:
    return isinstance(s, ast.If) and len(s.body) == 1 and isinstance(s.body[0], ast.Break) and not s.orelse


def real_var(name: str) -> str:
    return f"make {name} a Real from the start ({name} = 0.0, or {name}: float = 0)"


FALLIBLE = {"Char", "ToCode", "ToInteger", "ToReal", "Sqrt", "Ln", "Log", "Log10", "Arcsin", "Arccos"}


def can_fail(node: ast.AST, functions) -> str:
    """What in an expression can stop the program or do Input/Output: an index, a division, a call."""
    for n in ast.walk(node):
        if isinstance(n, ast.Subscript):
            return f"the index in {ast.unparse(n)}"
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Div, ast.Mod)):
            return f"the division in {ast.unparse(n)}"
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and (n.func.id in functions
                                                                         or n.func.id in FALLIBLE):
            return ast.unparse(n)
    return ""


def is_do(s: ast.stmt) -> bool:
    return isinstance(s, ast.While) and isinstance(s.test, ast.Constant) and s.test.value is True


AFTER_LOOP = ("after a for loop Flowgorithm's counter is one step past Python's last value; give the variable "
              "a new value first, or keep the value you need in another variable inside the loop")


def first_read(node: ast.AST, names) -> Optional[ast.Name]:
    """The first place (in source order) where `node` reads one of `names`."""
    hits = [n for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in names]
    return min(hits, key=lambda n: (n.lineno, n.col_offset), default=None)


def stored(st: ast.stmt) -> set[str]:
    """The variables a simple statement gives a value."""
    if isinstance(st, ast.AnnAssign) and st.value is None:
        return set()
    return {n.id for n in ast.walk(st) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}


def assigned(stmts: list) -> set[str]:
    """The variables the statements give a value on every path through them."""
    out: set[str] = set()
    for st in stmts:
        if isinstance(st, ast.If):
            out |= assigned(st.body) & assigned(st.orelse)
        elif isinstance(st, ast.While):
            if is_do(st):
                out |= assigned(st.body)
        elif not isinstance(st, ast.For):
            out |= stored(st)
    return out


def exposed_read(stmts: list, names) -> Optional[ast.Name]:
    """A read of one of `names` that the statements can reach before they give that name a value."""
    names = set(names)
    for st in stmts:
        if not names:
            break
        if isinstance(st, ast.If):
            hit = first_read(st.test, names) or exposed_read(st.body, names) or exposed_read(st.orelse, names)
            names -= assigned(st.body) & assigned(st.orelse)
        elif isinstance(st, ast.While):
            hit = first_read(st.test, names) or exposed_read(st.body, names)
            if is_do(st):
                names -= assigned(st.body)
        elif isinstance(st, ast.For):
            hit = first_read(st.iter, names) or exposed_read(st.body, names - {st.target.id})
        else:
            hit = first_read(st, names)
            names -= stored(st)
        if hit is not None:
            return hit
    return None


def changed(stmts: list) -> set[str]:
    """The variables the statements give new values, and the arrays whose elements they change."""
    out: set[str] = set()
    for st in stmts:
        for n in ast.walk(st):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                out.add(n.id)
            elif isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Name):
                out.add(n.value.id)
    return out


def stores(stmts: list, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)
               for st in stmts for n in ast.walk(st))


class FunctionConverter:
    """Converts one function of the program (main() included) into a Flowgorithm Function."""

    def __init__(self, builder: "ProgramBuilder", func: "FuncInfo"):
        self.b = builder
        self.m = builder.module
        self.f = func
        self.vars: dict[str, VarInfo] = {}
        self.ns = Namespace()
        self.counter = 0
        self.consumed: set[int] = set(self.m.skipped_lines)
        self.ret_var: Optional[VarInfo] = None
        self.ret_type: FgType = func.ret_type
        self.loop_vars: list[str] = []  # variables of the enclosing for loops
        # loop variables whose for loop has ended (on some path) and that got no new value since, with
        # the line of that loop: they hold Flowgorithm's final counter value, one step past Python's
        self.after_loop: dict[str, int] = {}
        self.warnings: list[Warning_] = []

    # ------------------------------------------------------------------ utils
    def err(self, msg: str, node: Optional[ast.AST], hint: str = "") -> ConvertError:
        return ConvertError(msg, node, hint, self.m.path)

    def warn(self, msg: str, node: Optional[ast.AST]) -> None:
        self.warnings.append(Warning_(msg, self.m.path, getattr(node, "lineno", None)))

    def next_order(self) -> int:
        self.counter += 1
        return self.counter

    # ------------------------------------------------------------ entry point
    def convert(self) -> Function:
        f, node = self.f, self.f.node
        params = []
        for p in f.params:
            fg = self.ns.reserve(legalize(p.name))
            self.vars[p.name] = VarInfo(p.name, fg, p.type, self.next_order(), is_param=True, declared=True)
            arr = isinstance(p.type, ArrayT)
            params.append(Param(fg, p.type.elem if arr else p.type, arr))
        body = list(f.body)
        self.check_structure(body)
        ret = body.pop() if body and isinstance(body[-1], ast.Return) else None
        value = ret.value if ret is not None else None
        if value is not None:
            if f.is_main:
                raise self.err("main() cannot return a value", ret)
            if self.ret_type == VOID:
                raise self.err(f"{f.name}() is annotated `-> None` but returns a value", ret)
            if isinstance(value, ast.Name) and stores(f.body, value.id) and value.id not in self.vars:
                # `return total`: total itself is the function's result variable
                self.ret_var = self.new_var(value.id, self.ret_type, value, declared=self.ret_type is not None)
        elif self.ret_type not in (None, VOID):
            raise self.err(f"{f.name}() is annotated `-> {py_name(self.ret_type)}` but does not end with "
                           "`return value`", node)
        else:
            self.ret_type = VOID

        doc: list = [Comment(f.docstring.strip())] if f.docstring and self.b.comments else []
        shapes: list = []
        head = header_end(self.m, node)
        shapes += self.take_comments(node.lineno, head)[0]  # `def f(a,  # note`
        end = node.end_lineno if ret is None else ret.lineno - 1
        shapes += self.block(body, head + 1, end, node.col_offset + 1)
        if value is not None:
            shapes += self.do_return(ret)
        if ret is not None:
            shapes += self.trailing_comments(ret.end_lineno, node.end_lineno, node.col_offset + 1)
        fn_type = self.ret_type if isinstance(self.ret_type, str) else VOID
        return Function(f.fg_name, fn_type, self.ret_var.fg if self.ret_var else "", params,
                        doc + self.declarations() + shapes)

    def check_structure(self, body: list) -> None:
        """Flowgorithm returns a function's result variable when the function ends: no early return."""
        for i, st in enumerate(body):
            for n in ast.walk(st):
                if isinstance(n, ast.Return) and not (n is st and i == len(body) - 1):
                    raise self.err("return must be the last statement of the function", n,
                                   "Flowgorithm functions end with their result: set a variable in the "
                                   "branches and return it at the end")
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                    raise self.err("functions, lambdas and classes are not defined inside a function", n)

    def declarations(self) -> list:
        """One Declare per scalar type at the top, then the values of the constants used."""
        out: list = []
        by_type: dict[str, list[str]] = {}
        for info in sorted(self.vars.values(), key=lambda v: v.order):
            if not info.is_param and not isinstance(info.type, ArrayT):
                by_type.setdefault(info.type, []).append(info.fg)
        for t, names in by_type.items():
            out.append(Declare(names, t))
        for info in sorted(self.vars.values(), key=lambda v: v.order):
            if info.is_const:
                out.append(Assign(info.fg, info.const_text))
        return out

    # --------------------------------------------------------------- comments
    def take_comments(self, start: int, end: int) -> tuple[list, bool]:
        """Comment shapes for the comment lines start..end."""
        items: list = []
        ignore = False
        for line in range(start, end + 1):
            if line in self.consumed or line not in self.m.comments:
                continue
            self.consumed.add(line)
            text = self.m.comments[line]
            d = parse_directive(text)
            if d is None:
                if self.b.comments and text.strip():
                    items.append(Comment(text.strip()))
            elif d[0] == "ignore":  # the ignore pre-pass applied every one that has a statement
                ignore = True
                self.warnings.append(Warning_("`# fg: ignore` is not followed by a statement of its block; "
                                              "nothing was left out", self.m.path, line))
            elif d[0] == "breakpoint":
                items.append(Breakpoint())
            elif d[0] == "comment":
                items.append(Comment(d[1]))
        return items, ignore

    def attach_comments(self, stmts: list, start_line: int, end_line: Optional[int], indent: int) -> list:
        """Comment shapes interleaved with the statements they precede, in source order."""
        items: list = []
        prev_end = start_line - 1
        for st in stmts:
            items += self.take_comments(prev_end + 1, header_end(self.m, st))[0] + [st]
            prev_end = trailing_end(self.m, st)
        return items + self.trailing_comments(prev_end, end_line, indent)

    def trailing_comments(self, prev_end: int, end_line: Optional[int], indent: int) -> list:
        """Comments after a block's last statement: up to end_line, plus the comment lines below it
        indented like the block (lines left out by `# fg: ignore` are skipped)."""
        last, ln = end_line or 0, prev_end + 1
        while ln <= len(self.m.lines):
            raw = self.m.lines[ln - 1]
            if not raw.strip():
                ln += 1
                continue
            if ln in self.consumed or (ln in self.m.comments and raw.lstrip().startswith("#")
                                       and indent_of(raw) >= indent):
                last = max(last, ln)
                ln += 1
                continue
            break
        return self.take_comments(prev_end + 1, last)[0] if last > prev_end else []

    # ------------------------------------------------------------- statements
    def block(self, stmts: list, start_line: int, end_line: Optional[int], indent: int) -> list:
        out: list = []
        for item in self.attach_comments(stmts, start_line, end_line, indent):
            out += self.stmt(item) if isinstance(item, ast.AST) else [item]
        return out

    def stmt(self, s: ast.stmt) -> list:
        handler = getattr(self, "s_" + type(s).__name__, None)
        if handler is None:
            kind = type(s).__name__
            word = {"ImportFrom": "import", "AsyncFunctionDef": "async def", "FunctionDef": "def",
                    "ClassDef": "class", "AsyncFor": "async for", "AsyncWith": "with", "TryStar": "try",
                    "TypeAlias": "type"}.get(kind, kind.lower())
            raise self.err(f"`{word}` statements are not part of the Flowgorithm dialect", s,
                           STATEMENT_HINTS.get(word, ""))
        return handler(s)

    def s_Pass(self, s: ast.Pass) -> list:
        return []

    def s_Break(self, s: ast.Break) -> list:
        raise self.err("break only ends a `while True:` loop (Flowgorithm's Do loop), as its last statement: "
                       "`if condition: break`", s)

    def s_Continue(self, s: ast.Continue) -> list:
        raise self.err("continue is not part of the Flowgorithm dialect", s, "put the rest of the loop body in an if")

    def s_Expr(self, s: ast.Expr) -> list:
        v = s.value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):  # a string on its own: a comment
            return [Comment(v.value.strip())] if self.b.comments else []
        if not isinstance(v, ast.Call):
            raise self.err("this expression does nothing on its own", s)
        name = v.func.id if isinstance(v.func, ast.Name) else None
        if name == "Output":
            return [self.output(v)]
        if name == "breakpoint" and not v.args:
            return [Breakpoint()]
        fi = self.b.functions.get(name) if name else None
        if fi is not None:
            return [Call(self.user_call(v, fi, statement=True).text)]
        if name == "Input":
            raise self.err("Input() reads into a variable: write `x = Input(int)`", s)
        if name in LIBRARY:
            raise self.err(f"the value of {name}() is not used", s)
        raise self.call_error(v)

    def output(self, call: ast.Call) -> Output:
        newline = True
        for kw in call.keywords:
            if kw.arg != "newline" or not (isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, bool)):
                raise self.err("Output() takes the values to show and `newline=True` or `newline=False`", call)
            newline = kw.value.value
        parts = []
        for a in call.args:
            if isinstance(a, ast.Starred):
                raise self.err("Output(*values) is not supported", a)
            e = self.expr(a)
            if isinstance(e.type, ArrayT):
                raise self.err("an array cannot be output; output its elements one by one", a)
            parts.append(paren(e, P_CAT))
        return Output(" & ".join(parts) if parts else '""', newline)

    def s_Assign(self, s: ast.Assign) -> list:
        if len(s.targets) != 1:
            raise self.err("assign one variable at a time", s)
        return self.assign(s.targets[0], s.value, s)

    def s_AnnAssign(self, s: ast.AnnAssign) -> list:
        if not isinstance(s.target, ast.Name):
            raise self.err("only a variable can be annotated", s)
        try:
            t = annotation_type(s.annotation)
        except ValueError as e:
            raise self.err(str(e), s.annotation) from None
        if s.value is None:
            if isinstance(t, ArrayT):
                raise self.err("an array needs its size: `xs: list[int] = [0] * n`", s)
            if s.target.id in self.vars:
                raise self.err(f"'{s.target.id}' already exists", s)
            self.new_var(s.target.id, t, s, declared=True)
            return []
        return self.assign(s.target, s.value, s, ann=t)

    def s_AugAssign(self, s: ast.AugAssign) -> list:
        load = ast.copy_location(ast.Name(id=s.target.id, ctx=ast.Load()), s.target) \
            if isinstance(s.target, ast.Name) else ast.copy_location(
                ast.Subscript(value=s.target.value, slice=s.target.slice, ctx=ast.Load()), s.target)
        value = ast.copy_location(ast.BinOp(left=load, op=s.op, right=s.value), s)
        return self.assign(s.target, value, s)

    def assign(self, target: ast.expr, value: ast.expr, s: ast.stmt, ann: FgType = None) -> list:
        if isinstance(target, (ast.Tuple, ast.List)):
            raise self.err("assign one variable at a time (Flowgorithm has no tuples)", s,
                           "to swap two values, use a third variable")
        if isinstance(target, ast.Subscript):
            text, elem = self.element(target)
            what = f"an element of {target.value.id}"
            real = f"make {target.value.id} an array of Reals from the start ({target.value.id} = [0.0] * n)"
            if self.is_input(value):
                self.check_input(elem, self.input_type(value), value, what, real)
                return [Input(text)]
            e = self.expr(value)
            self.check_store(elem, e.type, value, what, real)
            return [Assign(text, e.text)]
        if not isinstance(target, ast.Name):
            raise self.err("only variables and array elements can be assigned", s)
        name = target.id
        if name in self.loop_vars:
            raise self.err(f"the loop variable '{name}' is changed inside its loop", target,
                           "Flowgorithm's For counts with it; use another variable")
        if self.is_input(value):
            kind = self.input_type(value)
            var = self.store(name, ann or kind, value, ann is not None)
            self.check_input(var.type, kind, value, f"'{name}'", real_var(name))
            return [Input(var.fg)]
        if self.is_array_value(value):
            return self.new_array(name, value, s, ann)
        e = self.expr(value)
        if isinstance(e.type, ArrayT):
            raise self.err("an array cannot be copied: make a new one with [0] * n and copy the elements "
                           "in a loop", value)
        var = self.store(name, ann or e.type, value, ann is not None)
        self.check_store(var.type, e.type, value, f"'{name}'", real_var(name))
        return [Assign(var.fg, e.text)]

    def store(self, name: str, t: FgType, node: ast.AST, annotated: bool) -> VarInfo:
        """The variable `name` gets a value of type t (it is created by its first assignment)."""
        self.after_loop.pop(name, None)
        info = self.vars.get(name)
        if info is None:
            if self.b.constant(name) is not None:
                raise self.err(f"'{name}' is a constant", node, "constants are not changed")
            return self.new_var(name, t, node, declared=annotated)
        if info.is_const:
            raise self.err(f"'{name}' is a constant", node, "constants are not changed")
        if isinstance(info.type, ArrayT):
            raise self.err(f"'{name}' is an array; assign its elements", node)
        if info.type is None:  # the result variable of a function without a return annotation
            info.type = t
            return info
        if annotated and info.type != t:
            raise self.err(f"'{name}' already exists as {type_name(info.type)}", node)
        return info

    def check_store(self, target: FgType, value: FgType, node: ast.AST, what: str, real: str) -> None:
        """Flowgorithm converts an Integer into a Real variable, nothing else. `real` says how to make
        the target a Real, for the hint."""
        if target == value or (target == REAL and value == INTEGER):
            return
        if target == INTEGER and value == REAL:
            raise self.err(f"{what} is an Integer but gets a Real", node, f"{real}, or {CUT}")
        raise self.err(f"{what} is {type_name(target)} but gets {type_name(value)}", node)

    def check_input(self, target: FgType, kind: FgType, node: ast.AST, what: str, real: str) -> None:
        """Flowgorithm's Input reads the type of its variable, so Input() must read exactly that."""
        if target != kind:
            raise self.err(f"{what} is {type_name(target)}: read it with Input({py_name(target)})", node,
                           f"or {real}" if (target, kind) == (INTEGER, REAL) else "")

    def new_var(self, name: str, t: FgType, node: ast.AST, declared: bool = False) -> VarInfo:
        want = legalize(name)
        fg = self.ns.reserve(want)
        if fg.lower() != want.lower():
            self.warn(f"variable '{name}' is called '{fg}' in the flowchart (Flowgorithm ignores case and has no "
                      f"underscores, so the name clashes with another one)", node)
        info = VarInfo(name, fg, t, self.next_order(), declared=declared)
        self.vars[name] = info
        return info

    @staticmethod
    def is_input(value: ast.expr) -> bool:
        return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "Input"

    def input_type(self, call: ast.Call) -> str:
        if not call.args and not call.keywords:
            return STRING
        a = call.args[0] if len(call.args) == 1 and not call.keywords else None
        if isinstance(a, ast.Name) and a.id in PY_TYPES:
            return PY_TYPES[a.id]
        raise self.err("Input() takes one type: Input(int), Input(float), Input(str) or Input(bool)", call,
                       "show a prompt with Output(...) before it")

    # ---------------------------------------------------------------- arrays
    @staticmethod
    def is_array_value(value: ast.expr) -> bool:
        return isinstance(value, ast.List) or (
            isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult)
            and (isinstance(value.left, ast.List) or isinstance(value.right, ast.List)))

    def new_array(self, name: str, value: ast.expr, s: ast.stmt, ann: FgType) -> list:
        if name in self.vars or self.b.constant(name) is not None:
            raise self.err(f"'{name}' already exists; an array is made once", s)
        if ann is not None and not isinstance(ann, ArrayT):
            raise self.err(f"'{name}' is annotated {type_name(ann)} but gets an array", s)
        if isinstance(value, ast.List):  # xs = [3, 1, 2]
            if not value.elts:
                raise self.err("an array needs a size: `xs = [0] * n`", s)
            elems = [self.expr(e) for e in value.elts]
            elem = ann.elem if ann is not None else elems[0].type
            for e, node in zip(elems, value.elts):
                self.check_store(elem, e.type, node, f"an element of {name}",
                                 f"write the first element as a Real ({name} = [1.0, ...])")
            var = self.new_var(name, ArrayT(elem), s, declared=ann is not None)
            return [Declare([var.fg], elem, True, str(len(elems)))] + [
                Assign(f"{var.fg}[{i}]", e.text) for i, e in enumerate(elems)]
        lst, n = (value.left, value.right) if isinstance(value.left, ast.List) else (value.right, value.left)
        try:
            if len(lst.elts) != 1:
                raise ValueError
            fill = literal_value(lst.elts[0])
        except ValueError:
            raise self.err("an array is made from one value: `[0] * n`, `[0.0] * n`, `[\"\"] * n` or "
                           "`[False] * n`", value) from None
        elem = ann.elem if ann is not None else value_type(fill)
        if fill != DEFAULT_FILL[elem] or (type(fill) is bool) != (elem == BOOLEAN):
            raise self.err(f"an array of {type_name(elem)} starts out as {literal_text(DEFAULT_FILL[elem])} in "
                           f"Flowgorithm: write [{repr(DEFAULT_FILL[elem]) if elem != STRING else chr(34) * 2}] * n",
                           lst.elts[0], "then set other values in a loop")
        size = self.expr(n)
        if size.type != INTEGER:
            raise self.err("the size of an array is an Integer", n)
        var = self.new_var(name, ArrayT(elem), s, declared=ann is not None)
        return [Declare([var.fg], elem, True, size.text)]

    def element(self, sub: ast.Subscript) -> tuple[str, str]:
        if not isinstance(sub.value, ast.Name):
            raise self.err("only array variables are indexed", sub)
        info = self.lookup(sub.value)
        if info.type == STRING:
            raise self.err("a character of a String is Char(text, i)", sub)
        if not isinstance(info.type, ArrayT):
            raise self.err(f"'{sub.value.id}' is not an array", sub)
        if isinstance(sub.slice, ast.Slice):
            raise self.err("slices are not part of the Flowgorithm dialect", sub)
        idx = self.expr(sub.slice)
        if idx.type != INTEGER:
            raise self.err(f"an array index is an Integer, not {type_name(idx.type)}", sub.slice,
                           CUT if idx.type == REAL else "")
        if re.fullmatch(r"-\d+", idx.text):
            raise self.err("Flowgorithm arrays have no negative indexes", sub.slice,
                           "the last element is xs[Size(xs) - 1]")
        return f"{info.fg}[{idx.text}]", info.type.elem

    # --------------------------------------------------------------- control
    def s_If(self, s: ast.If) -> list:
        cond = self.condition(s.test)
        head = header_end(self.m, s)
        col = s.col_offset + 1
        before = dict(self.after_loop)
        if not s.orelse:
            then = self.block(s.body, head + 1, s.end_lineno, col)
            self.after_loop = {**before, **self.after_loop}
            return [If(cond, then, [])]
        body_end = s.body[-1].end_lineno if s.body else head
        else_line = find_else_line(self.m, s.col_offset, body_end + 1, s.orelse[0].lineno) or s.orelse[0].lineno
        then = self.block(s.body, head + 1, else_line - 1, col)
        after_then, self.after_loop = self.after_loop, before
        other = self.block(s.orelse, else_line, s.end_lineno, col)
        self.after_loop = {**after_then, **self.after_loop}
        return [If(cond, then, other)]

    def s_While(self, s: ast.While) -> list:
        if s.orelse:
            raise self.err("while ... else is not part of the Flowgorithm dialect", s)
        head = header_end(self.m, s)
        col = s.col_offset + 1
        if is_do(s):  # Flowgorithm's Do loop
            if not s.body or not is_break_if(s.body[-1]):
                raise self.err("`while True:` is Flowgorithm's Do loop: its last statement is `if condition: break`",
                               s, "for a loop that tests first, write `while condition:`")
            brk = s.body[-1]
            body = self.block(s.body[:-1], head + 1, brk.lineno - 1, col)
            tail = self.take_comments(brk.lineno, trailing_end(self.m, s))[0]
            cond = self.negate(brk.test)
            self.check_next_round(s)
            return [Do(cond, body + tail)]
        cond = self.condition(s.test)
        before = dict(self.after_loop)
        body = self.block(s.body, head + 1, s.end_lineno, col)
        self.check_next_round(s, s.test)
        self.after_loop = {**before, **self.after_loop}
        return [While(cond, body)]

    def check_next_round(self, loop: ast.stmt, test: Optional[ast.expr] = None) -> None:
        """A loop's next round starts with the variables as its body left them: one that an inner for
        loop left with its final counter value must get a new value before it is read again."""
        own = loop.target.id if isinstance(loop, ast.For) else None
        stale = {k: line for k, line in self.after_loop.items() if k != own}
        hit = (first_read(test, stale) if test is not None else None) or exposed_read(loop.body, stale)
        if hit is not None:
            raise self.err(f"'{hit.id}' is read here when the loop repeats, after its for loop (line {stale[hit.id]})",
                           hit, AFTER_LOOP)

    def s_For(self, s: ast.For) -> list:
        if s.orelse:
            raise self.err("for ... else is not part of the Flowgorithm dialect", s)
        it = s.iter
        if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"
                and not it.keywords and 1 <= len(it.args) <= 3):
            raise self.err("a for loop counts with range(): `for i in range(n)`, `range(a, b)` or `range(a, b, step)`",
                           s, "to go through an array: for i in range(Size(xs))")
        if not isinstance(s.target, ast.Name):
            raise self.err("a for loop has one variable", s)
        name = s.target.id
        if name in self.loop_vars:
            raise self.err(f"'{name}' is already the variable of an enclosing for loop", s.target,
                           "give the inner loop another variable")
        args = it.args
        start = self.expr(args[0]) if len(args) > 1 else Ex("0", P_ATOM, INTEGER)
        stop_node = args[0] if len(args) == 1 else args[1]
        stop = self.expr(stop_node)
        step = 1
        if len(args) == 3:
            try:
                step = literal_value(args[2])
            except ValueError:
                raise self.err("the step of range() is written as a number (like 2 or -1)", args[2]) from None
            if type(step) is not int or step == 0:
                raise self.err("the step of range() is a whole number other than 0", args[2])
        for e, node in ((start, args[0]), (stop, stop_node)):
            if e.type != INTEGER:
                raise self.err(f"range() counts with Integers, not {type_name(e.type)}", node,
                               CUT if e.type == REAL else "")
        inner = {id(t) for st in s.body for n in ast.walk(st) if isinstance(n, ast.For) for t in ast.walk(n.target)}
        if any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store) and id(n) not in inner
               for st in s.body for n in ast.walk(st)):
            raise self.err(f"the loop variable '{name}' is changed inside its loop", s,
                           "Flowgorithm's For counts with it; use another variable")
        var = self.vars.get(name)
        if var is None:
            var = self.new_var(name, INTEGER, s.target)
        elif var.type != INTEGER or var.is_const:
            raise self.err(f"'{name}' is not an Integer variable", s.target)
        sized = {id(c.args[0]) for c in ast.walk(stop_node) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id == "Size" and c.args}  # an array's size is fixed
        moved = sorted({n.id for n in ast.walk(stop_node) if isinstance(n, ast.Name) and id(n) not in sized}
                       & changed(s.body))
        if moved:
            raise self.err(f"the loop changes '{moved[0]}', which range() counts to", stop_node,
                           "Python fixes the end of range() when the loop starts; copy it into a variable "
                           "the loop does not change")
        end = plus(stop, -1 if step > 0 else 1)
        self.after_loop.pop(name, None)
        before = dict(self.after_loop)
        self.loop_vars.append(name)
        try:
            body = self.block(s.body, header_end(self.m, s) + 1, s.end_lineno, s.col_offset + 1)
        finally:
            self.loop_vars.pop()
        self.check_next_round(s)
        self.after_loop = {**before, **self.after_loop, name: s.lineno}
        return [For(var.fg, start.text, end, "inc" if step > 0 else "dec", str(abs(step)), body)]

    def do_return(self, s: ast.Return) -> list:
        e = self.expr(s.value)
        if isinstance(e.type, ArrayT):
            raise self.err("Flowgorithm functions cannot return arrays", s.value)
        if self.ret_type is None:
            self.ret_type = e.type
        else:
            self.check_store(self.ret_type, e.type, s.value, f"the result of {self.f.name}()",
                             f"let it return a Real (def {self.f.name}(...) -> float:)")
        if self.ret_var is not None and isinstance(s.value, ast.Name) and self.vars.get(s.value.id) is self.ret_var:
            if self.ret_var.type is None:  # pragma: no cover - always assigned before
                self.ret_var.type = self.ret_type
            self.ret_type = self.ret_var.type if self.f.ret_type is None else self.ret_type
            return []
        used = {n.id.lower() for n in ast.walk(self.f.node) if isinstance(n, ast.Name)}
        name, k = "result", 1
        while name in used:
            k += 1
            name = f"result{k}"
        self.ret_var = VarInfo("<result>", self.ns.reserve(name), self.ret_type, self.next_order())
        self.vars["<result>"] = self.ret_var
        return [Assign(self.ret_var.fg, e.text)]

    # ----------------------------------------------------------- conditions
    def condition(self, node: ast.expr) -> str:
        e = self.expr(node)
        if e.type != BOOLEAN:
            raise self.err(f"a condition is true or false, not {type_name(e.type)}", node,
                           "compare explicitly, e.g. `n != 0`")
        return e.text

    def negate(self, node: ast.expr) -> str:
        """`not cond`, simplified for one comparison (`x > 0` -> `x <= 0`)."""
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in FLIP_COMPARE:
            flipped = ast.copy_location(ast.Compare(left=node.left, ops=[FLIP_COMPARE[type(node.ops[0])]()],
                                                    comparators=node.comparators), node)
            return self.condition(flipped)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self.condition(node.operand)
        e = self.expr(node)
        if e.type != BOOLEAN:
            raise self.err(f"a condition is true or false, not {type_name(e.type)}", node)
        return f"not {paren(e, P_UNARY)}"

    # ----------------------------------------------------------- expressions
    def expr(self, node: ast.expr) -> Ex:
        handler = getattr(self, "e_" + type(node).__name__, None)
        if handler is None:
            what = {"JoinedStr": "f-strings", "IfExp": "conditional expressions", "ListComp": "list comprehensions",
                    "Dict": "dictionaries", "Tuple": "tuples", "Lambda": "lambdas",
                    "Attribute": "attributes and methods", "List": "lists inside expressions",
                    "NamedExpr": "assignment expressions (:=)", "Set": "sets", "Await": "await"}.get(
                type(node).__name__, type(node).__name__)
            hint = {"JoinedStr": "pass the values to Output(...), or join Strings with + and ToString(...)",
                    "IfExp": "use an if statement"}.get(type(node).__name__, "")
            raise self.err(f"{what} are not part of the Flowgorithm dialect", node, hint)
        return handler(node)

    def e_Constant(self, n: ast.Constant) -> Ex:
        v = n.value
        if isinstance(v, bool):
            return Ex("true" if v else "false", P_ATOM, BOOLEAN)
        if isinstance(v, int):
            return Ex(str(v), P_ATOM, INTEGER)
        if isinstance(v, float):
            try:
                return Ex(float_text(v), P_ATOM, REAL)
            except ValueError as e:
                raise self.err(str(e), n) from None
        if isinstance(v, str):
            return string_literal(v)
        raise self.err(f"{v!r} is not part of the Flowgorithm dialect", n)

    def e_Name(self, n: ast.Name) -> Ex:
        if n.id == "pi" and n.id not in self.vars:
            return Ex("pi", P_ATOM, REAL)
        info = self.lookup(n)
        return Ex(info.fg, P_ATOM, info.type)

    def lookup(self, n: ast.Name) -> VarInfo:
        info = self.vars.get(n.id)
        if info is not None:
            if n.id in self.after_loop:
                raise self.err(f"'{n.id}' is read after its for loop (line {self.after_loop[n.id]})", n, AFTER_LOOP)
            return info
        const = self.b.constant(n.id)
        if const is not None:  # a module constant: declared and set in every function that uses it
            info = VarInfo(n.id, self.ns.reserve(legalize(n.id)), value_type(const), self.next_order(),
                           is_const=True, const_text=literal_text(const), declared=True)
            self.vars[n.id] = info
            return info
        if n.id in self.b.functions:
            raise self.err(f"{n.id}() is called with parentheses", n)
        if n.id in PY_TYPES or n.id in LIBRARY or n.id in ("Output", "Input"):
            raise self.err(f"'{n.id}' is not a value", n)
        raise self.err(f"'{n.id}' is used before it gets a value", n)

    def e_UnaryOp(self, n: ast.UnaryOp) -> Ex:
        e = self.expr(n.operand)
        if isinstance(n.op, ast.Not):
            if e.type != BOOLEAN:
                raise self.err("`not` needs true or false", n)
            return Ex(f"not {paren(e, P_UNARY)}", P_UNARY, BOOLEAN)
        if not is_numeric(e.type):
            raise self.err("a sign needs a number", n)
        if isinstance(n.op, ast.UAdd):
            return e
        if isinstance(n.op, ast.USub):
            inner = paren(e, P_UNARY)
            return Ex(f"-({inner})" if inner.startswith("-") else f"-{inner}", P_UNARY, e.type)
        raise self.err("bitwise operators are not part of the Flowgorithm dialect", n)

    def e_BinOp(self, n: ast.BinOp) -> Ex:
        a, b = self.expr(n.left), self.expr(n.right)
        op = type(n.op)
        if op is ast.Add and STRING in (a.type, b.type):
            if a.type != STRING or b.type != STRING:
                raise self.err("a String and a number are joined with ToString(): `\"n = \" + ToString(n)`", n,
                               "or pass both to Output(\"n = \", n)")
            return Ex(f"{paren(a, P_CAT)} & {paren(b, P_CAT, 'right')}", P_CAT, STRING)
        if op is ast.FloorDiv:
            raise self.err("// is not part of the Flowgorithm dialect", n, "write Int(a / b)")
        if op not in OPERATORS:
            raise self.err("bitwise operators are not part of the Flowgorithm dialect", n)
        sym, prec = OPERATORS[op]
        for e, node in ((a, n.left), (b, n.right)):
            if not is_numeric(e.type):
                raise self.err(f"{sym} needs numbers, not {type_name(e.type)}", node)
        if op is ast.Pow:
            # Integer only for a whole-number exponent written out (n ** 2): 2 ** n is a Real for n < 0
            whole = isinstance(n.right, ast.Constant) and type(n.right.value) is int
            t = INTEGER if a.type == INTEGER and whole else REAL
            # a sign binds tighter than ^ in Flowgorithm: (-2) ^ 2 is written with its parentheses
            left, right = (f"({e.text})" if e.prec == P_UNARY else paren(e, prec, side)
                           for e, side in ((a, "left"), (b, "right")))
            return Ex(f"{left} ^ {right}", prec, t)
        t = REAL if op is ast.Div or REAL in (a.type, b.type) else INTEGER
        return Ex(f"{paren(a, prec)} {sym} {paren(b, prec, 'right')}", prec, t)

    def e_BoolOp(self, n: ast.BoolOp) -> Ex:
        word, prec = ("and", P_AND) if isinstance(n.op, ast.And) else ("or", P_OR)
        parts = []
        for v in n.values:
            e = self.expr(v)
            if e.type != BOOLEAN:
                raise self.err(f"`{word}` needs true or false on both sides, not {type_name(e.type)}", v,
                               "compare explicitly, e.g. `n != 0`")
            parts.append(paren(e, prec))
        for v in n.values[1:]:
            what = can_fail(v, self.b.functions)
            if what:
                self.warn(f"Python skips the right side of `{word}` when the left side is "
                          f"{'false' if word == 'and' else 'true'}, Flowgorithm may evaluate it anyway: {what} "
                          "must work then too, or go into a nested if", v)
                break
        return Ex(f" {word} ".join(parts), prec, BOOLEAN)

    def e_Compare(self, n: ast.Compare) -> Ex:
        if len(n.ops) != 1:
            raise self.err("compare two values at a time: `a < b and b < c`", n)
        op = type(n.ops[0])
        if op not in COMPARE_OP:
            raise self.err(f"`{type(n.ops[0]).__name__.lower()}` comparisons are not part of the Flowgorithm "
                           "dialect", n, "compare with ==, !=, <, <=, > or >=")
        a, b = self.expr(n.left), self.expr(n.comparators[0])
        if isinstance(a.type, ArrayT) or isinstance(b.type, ArrayT) or not (
                a.type == b.type or (is_numeric(a.type) and is_numeric(b.type))):
            raise self.err(f"cannot compare {type_name(a.type)} with {type_name(b.type)}", n)
        if a.type == BOOLEAN and op not in (ast.Eq, ast.NotEq):
            raise self.err("true and false are compared with == and != only", n)
        if a.type == STRING and op not in (ast.Eq, ast.NotEq):
            self.warn('Python orders Strings by character code ("B" < "a"); Flowgorithm may order upper and lower '
                      "case, digits and punctuation differently", n)
        return Ex(f"{paren(a, P_REL)} {COMPARE_OP[op]} {paren(b, P_REL, 'right')}", P_REL, BOOLEAN)

    def e_Subscript(self, n: ast.Subscript) -> Ex:
        text, elem = self.element(n)
        return Ex(text, P_ATOM, elem)

    def e_Call(self, n: ast.Call) -> Ex:
        name = n.func.id if isinstance(n.func, ast.Name) else None
        fi = self.b.functions.get(name) if name else None
        if fi is not None:
            return self.user_call(n, fi)
        if name in LIBRARY:
            return self.library_call(name, n)
        if name == "Input":
            raise self.err("Input() is the whole value of an assignment: `x = Input(int)`", n)
        if name == "Output":
            raise self.err("Output() is a statement of its own", n)
        raise self.call_error(n)

    def call_error(self, n: ast.Call) -> ConvertError:
        fn = n.func
        if isinstance(fn, ast.Name):
            hint = INSTEAD.get(fn.id, "")
            arg = n.args[0] if len(n.args) == 1 else None
            if fn.id in PY_TYPES and isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) \
                    and arg.func.id == "input":
                hint = f"read it with x = Input({fn.id}); show the question with Output(...) first"
            return self.err(f"{fn.id}() is not part of the Flowgorithm dialect", n, hint)
        if isinstance(fn, ast.Attribute):
            return self.err(f"methods such as .{fn.attr}() are not part of the Flowgorithm dialect", n,
                            "Flowgorithm has functions only: Len, Char, ToCode, ... (see the flowgorithm library)")
        return self.err("this call is not part of the Flowgorithm dialect", n)

    def library_call(self, name: str, n: ast.Call) -> Ex:
        kinds, result = LIBRARY[name]
        if n.keywords or len(n.args) != len(kinds):
            raise self.err(f"{name}() takes {len(kinds)} argument{'s' if len(kinds) != 1 else ''}", n)
        texts = []
        types = []
        for a, kind in zip(n.args, kinds):
            e = self.expr(a)
            bad = (kind == NUM and not is_numeric(e.type) or kind in (INTEGER, STRING) and e.type != kind
                   or kind == ARRAY and not isinstance(e.type, ArrayT) or kind == ANY and isinstance(e.type, ArrayT))
            if bad:
                what = {NUM: "a number", INTEGER: "an Integer", STRING: "a String", ARRAY: "an array",
                        ANY: "a value"}[kind]
                raise self.err(f"{name}() needs {what}, not {type_name(e.type)}", a,
                               ARG_HINTS.get(name) or (CUT if kind == INTEGER and e.type == REAL else ""))
            texts.append(e.text)
            types.append(e.type)
        return Ex(f"{name}({', '.join(texts)})", P_ATOM, result or types[0])

    def user_call(self, n: ast.Call, fi: "FuncInfo", statement: bool = False) -> Ex:
        if fi.is_main:
            raise self.err("main() is the program; it is not called", n)
        if n.keywords or any(isinstance(a, ast.Starred) for a in n.args):
            raise self.err("arguments are passed by position, one by one", n)
        if len(n.args) != len(fi.params):
            raise self.err(f"{fi.name}() takes {len(fi.params)} argument{'s' if len(fi.params) != 1 else ''}, "
                           f"not {len(n.args)}", n)
        if fi.ret_type is None:
            raise self.err(f"the type {fi.name}() returns is not known here (it calls itself)", n,
                           f"annotate it: def {fi.name}(...) -> int:")
        if not statement and fi.ret_type == VOID:
            raise self.err(f"{fi.name}() returns no value", n)
        texts = []
        for a, p in zip(n.args, fi.params):
            e = self.expr(a)
            if isinstance(p.type, ArrayT):
                if not (isinstance(a, ast.Name) and e.type == p.type):
                    raise self.err(f"parameter '{p.name}' of {fi.name}() is an array of {type_name(p.type.elem)}", a)
            else:
                self.check_store(p.type, e.type, a, f"parameter '{p.name}' of {fi.name}()",
                                 f"make the parameter a Real ({p.name}: float)")
            texts.append(e.text)
        return Ex(f"{fi.fg_name}({', '.join(texts)})", P_ATOM, fi.ret_type)


def plus(e: Ex, k: int) -> str:
    """Text of `e + k` (k = ±1), folding literals: range(n) ends at n - 1, range(1, n + 1) at n."""
    if re.fullmatch(r"-?\d+", e.text):
        return str(int(e.text) + k)
    m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?) ([+-]) (\d+)", e.text)
    if m:
        c = int(m.group(3)) * (1 if m.group(2) == "+" else -1) + k
        return m.group(1) if c == 0 else f"{m.group(1)} {'+' if c > 0 else '-'} {abs(c)}"
    return f"{paren(e, P_ADD)} {'+' if k > 0 else '-'} {abs(k)}"
