"""Convert one Python function (or a module's top-level code) into a Flowgorithm Function."""
from __future__ import annotations

import ast
import copy
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .layout import find_else_line, header_end, indent_of, parse_directive, trailing_end  # noqa: F401
from .model import (ArrayT, Assign, BOOLEAN, Breakpoint, Call, Comment, ConvertError, Declare, Do,
                    FgType, For, Function, INTEGER, If, Input, Namespace, Output, P_ADD, P_AND, P_ATOM,
                    P_CAT, P_MUL, P_OR, P_POW, P_REL, P_UNARY, Param, REAL, STRING, VOID, Warning_, While,
                    is_numeric, join_types, legalize, type_name)

if TYPE_CHECKING:  # pragma: no cover
    from .project import FuncInfo, ModuleInfo, ProgramBuilder

FLIP_COMPARE = {ast.Eq: "!=", ast.NotEq: "==", ast.Lt: ">=", ast.LtE: ">", ast.Gt: "<=", ast.GtE: "<"}
COMPARE_OP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}

# python math.* name -> (format template, result type)
MATH_FUNCS = {
    "sqrt": ("Sqrt({0})", REAL), "sin": ("Sin({0})", REAL), "cos": ("Cos({0})", REAL),
    "tan": ("Tan({0})", REAL), "asin": ("Arcsin({0})", REAL), "acos": ("Arccos({0})", REAL),
    "atan": ("Arctan({0})", REAL), "log": ("Ln({0})", REAL), "log10": ("Log10({0})", REAL),
    "fabs": ("Abs({0})", REAL), "trunc": ("Int({0})", INTEGER), "floor": ("Int({0})", INTEGER),
}
DEFAULT_VALUES = {INTEGER: {0}, REAL: {0, 0.0}, STRING: {""}, BOOLEAN: {False}}


def float_literal(v: float) -> tuple[str, int]:
    """Flowgorithm text (and precedence) for a float. Flowgorithm has no exponent notation: numbers
    that Python writes with one become plain decimals when that stays short (1e-05 -> 0.00001),
    else mantissa * 10 ^ exponent (1.602176634e-19 -> 1.602176634 * 10 ^ -19; `10.0` for positive
    exponents, so that the power is a Real and cannot overflow Flowgorithm's Integer)."""
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{v!r} is not supported")
    s = repr(v)
    if "e" not in s:
        return s, (P_UNARY if s.startswith("-") else P_ATOM)
    mantissa, exp = s.split("e")
    e = int(exp)
    if -7 <= e <= 18:  # a plain decimal, exactly the digits Python shows
        digits = mantissa.lstrip("-").replace(".", "")
        point = len(mantissa.lstrip("-").split(".")[0]) + e
        text = ("0." + "0" * -point + digits if point <= 0 else
                digits[:point].ljust(point, "0") + "." + (digits[point:] or "0"))
        return ("-" if mantissa.startswith("-") else "") + text, (P_UNARY if mantissa.startswith("-") else P_ATOM)
    if e < -300:  # 10 ^ e alone would underflow: scale in two steps (denormals)
        return f"{mantissa} * 10 ^ -300 * 10 ^ {e + 300}", P_MUL
    power = f"10 ^ {e}" if e < 0 else f"10.0 ^ {e}"
    if mantissa == "1":
        return power, P_POW
    if mantissa == "-1":  # Flowgorithm's unary minus binds tighter than ^
        return f"-({power})", P_UNARY
    return f"{mantissa} * {power}", P_MUL


def literal_text(value) -> str:
    """Flowgorithm text for a Python literal (int, float, bool, str)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return float_literal(value)[0]
    if isinstance(value, str):
        return string_literal(value)[0]
    raise TypeError(f"unsupported literal {value!r}")


def string_literal(s: str) -> tuple[str, int]:
    """A Flowgorithm string literal; quotes and control characters go through ToChar()."""
    parts: list[str] = []
    buf = ""
    for ch in s:
        if ch == '"' or ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF or ord(ch) in (0xFFFE, 0xFFFF):
            if buf:
                parts.append(f'"{buf}"')
                buf = ""
            parts.append(f"ToChar({ord(ch)})")
        else:
            buf += ch
    if buf:
        parts.append(f'"{buf}"')
    if not parts:
        return '""', P_ATOM
    if len(parts) == 1:
        return parts[0], P_ATOM
    return " & ".join(parts), P_CAT


@dataclass
class VarInfo:
    py: str
    fg: str
    type: FgType = None
    is_param: bool = False
    is_array: bool = False
    is_const: bool = False
    const_text: str = ""
    order: int = 0
    declared: FgType = None  # the annotated type; None when the type is inferred (and may widen)
    node: Optional[ast.AST] = None  # first assignment, for error locations


def assignable(target: FgType, value: FgType) -> bool:
    """Can a value of type `value` be stored in a variable declared `target` without losing data?"""
    return target == value or (target == REAL and value == INTEGER)


def py_type(t: FgType) -> str:
    """The Python spelling of a Flowgorithm type, for messages about annotations."""
    names = {INTEGER: "int", REAL: "float", STRING: "str", BOOLEAN: "bool"}
    if isinstance(t, ArrayT):
        return f"list[{names.get(t.elem, t.elem)}]"
    return names.get(t, type_name(t))


def has_break_or_continue(stmts: list[ast.stmt]) -> bool:
    """True if a break/continue in these statements would act on the enclosing loop."""
    for s in stmts:
        if isinstance(s, (ast.Break, ast.Continue)):
            return True
        if isinstance(s, ast.If):
            if has_break_or_continue(s.body) or has_break_or_continue(s.orelse):
                return True
        # nested loops own their own break/continue; nested defs are errors anyway
    return False


def ast_only(stmts: list) -> list[ast.stmt]:
    """Statement lists may carry Comment/Breakpoint shapes between statements; drop them."""
    return [x for x in stmts if isinstance(x, ast.AST)]


def contains_return(stmts: list) -> bool:
    for s in ast_only(stmts):
        for n in ast.walk(s):
            if isinstance(n, ast.Return):
                return True
    return False


def ends_with_return(stmts: list) -> bool:
    stmts = ast_only(stmts)
    if not stmts:
        return False
    last = stmts[-1]
    if isinstance(last, ast.Return):
        return True
    if isinstance(last, ast.If):
        return ends_with_return(last.body) and ends_with_return(last.orelse)
    return False


def may_return(stmts: list) -> bool:
    """True if some path through these statements (if-chains only) returns."""
    for s in ast_only(stmts):
        if isinstance(s, ast.Return):
            return True
        if isinstance(s, ast.If) and (may_return(s.body) or may_return(s.orelse)):
            return True
    return False


def is_true_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is True or (
        isinstance(node, ast.Constant) and type(node.value) is int and node.value != 0)


def has_call(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) for n in ast.walk(node))


def is_break_if(s: ast.stmt) -> bool:
    return (isinstance(s, ast.If) and len(s.body) == 1 and isinstance(s.body[0], ast.Break)
            and not s.orelse)


def is_list_display(node: ast.AST) -> bool:
    """`[...]`, a list comprehension or `[x] * n`."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return isinstance(node.left, ast.List) or isinstance(node.right, ast.List)
    return isinstance(node, (ast.List, ast.ListComp))


def assigned_names(stmts: list) -> set[str]:
    """Names bound anywhere in these statements: Python makes them local to the whole function."""
    names: set[str] = set()
    for st in stmts:
        if isinstance(st, ast.AST):
            for n in ast.walk(st):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    names.add(n.id)
    return names


def paren(text_prec: tuple[str, int], prec: int, side: str = "left") -> str:
    """An operand's text, parenthesised when it binds less tightly than its context needs."""
    t, p = text_prec
    if p < prec or (p == prec and (side == "right" or prec == P_POW)):
        return f"({t})"
    return t


def reads_name(loop: ast.stmt, name: str, skip: ast.AST) -> bool:
    """Does a loop (its condition or its body) read `name` anywhere outside the statement `skip`?"""
    stack = [x for x in ([loop.test] if isinstance(loop, ast.While) else []) + list(loop.body)
             if isinstance(x, ast.AST)]
    while stack:
        n = stack.pop()
        if n is skip:
            continue
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load):
            return True
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
            return True
        stack.extend(ast.iter_child_nodes(n))
    return False


def const_str(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class FunctionConverter:
    """Converts the body of one FuncInfo into Flowgorithm shapes.

    `hints` are the final variable types of a previous pass over the same function: a variable
    that widens from Integer to Real late in the body (`balance = balance * 1.05` in a loop) must
    be Real from its first use on, so the builder converts again with the widened types (`widened`
    tells it whether that is needed). `hidden_loops` are the for loops (by id) whose variable a
    previous pass saw read after the loop: they count with a hidden variable (see s_For).
    """

    def __init__(self, builder: "ProgramBuilder", module: "ModuleInfo", func: "FuncInfo",
                 hints: Optional[dict[str, FgType]] = None, hidden_loops: frozenset = frozenset()):
        self.b = builder
        self.m = module
        self.f = func
        self.filename = module.path
        self.hints = hints or {}
        self.hidden_loops = hidden_loops
        self.vars: dict[str, VarInfo] = {}
        self.ns = Namespace()
        self.ret_var: Optional[VarInfo] = None
        self.ret_types: list[FgType] = []
        self.consumed: set[int] = set(module.skipped_lines)
        self.loop_depth = 0
        self.counter = 0
        self.loop_stack: list[ast.stmt] = []  # the loops around the statement being converted
        self.loop_counters: list[tuple[VarInfo, ast.AST]] = []
        # A For that counts with the Python variable leaves Flowgorithm's final counter value in it
        # (not Python's last value): name -> ids of such loops whose value it may still hold.
        self.stale: dict[str, set[int]] = {}
        self.read_after: set[int] = set()  # loops whose variable was read in that state
        # Statements an expression needs before its own statement (`x = 1 + int(input())`).
        self.pre: list = []
        self.effects = 0  # calls with side effects already emitted in place in this statement
        self.conditional = 0  # inside the right operand of and/or (evaluated only sometimes)
        self.locals: Optional[set[str]] = None
        self.reads: Optional[set[str]] = None
        self.intdiv_warned = False
        self.widened = False
        self.warnings: list[Warning_] = []

    # ------------------------------------------------------------------ utils
    def err(self, msg: str, node: Optional[ast.AST], hint: str = "") -> ConvertError:
        return ConvertError(msg, node, hint, self.filename)

    def warn(self, msg: str, node: Optional[ast.AST]) -> None:
        self.warn_at(msg, getattr(node, "lineno", None))

    def warn_at(self, msg: str, lineno: Optional[int]) -> None:
        self.warnings.append(Warning_(msg, self.filename, lineno))

    def next_order(self) -> int:
        self.counter += 1
        return self.counter

    def type_hints(self) -> dict[str, FgType]:
        """Final types of the named variables, as hints for another pass."""
        return {k: v.type for k, v in self.vars.items() if not k.startswith("<") and v.type is not None}

    # ------------------------------------------------------------ entry point
    def convert(self) -> Function:
        f = self.f
        params: list[Param] = []
        for p in f.params:
            t = p.type
            if p.declared is None and isinstance(self.hints.get(p.py_name), str):
                t = join_types(t, self.hints[p.py_name])  # an inferred parameter widened by the body
            if t is None:
                raise self.err(f"parameter '{p.py_name}' of {f.py_name}() needs a type annotation",
                               f.node, "write e.g. `def f(n: int, name: str, xs: list[float])`")
            fg = self.ns.reserve(legalize(p.py_name))
            arr = isinstance(t, ArrayT)
            self.vars[p.py_name] = VarInfo(p.py_name, fg, t, is_param=True, is_array=arr,
                                           order=self.next_order(), declared=p.declared, node=f.node)

        if f.ret_type != VOID:  # returns a value (type may still be unknown)
            self.ret_var = self.make_return_var()

        header_comment: list = []
        if f.docstring and self.b.comments_enabled:
            header_comment.append(Comment(f.docstring.strip()))

        if f.node is not None:
            head = header_end(self.m, f.node)
            def_comments, _ = self.take_comments(f.node.lineno, head)  # `def f(a,  # note`
            body_ir = def_comments + self.block(f.body, head + 1, f.node.end_lineno, f.node.col_offset + 1)
        else:  # module-level program, or the `if __name__ == "__main__":` block
            start, end, indent = f.span or (1, len(self.m.lines), 0)
            body_ir = self.block(f.body, start, end, indent)
        for var, _ in self.loop_counters:
            if var.type != INTEGER:  # used as a Real elsewhere: the next pass counts with a copy
                self.widened = True
        for p in f.params:  # callers must see a parameter type that the body widened
            info = self.vars[p.py_name]
            if p.declared is None:
                p.type = info.type
            arr = isinstance(info.type, ArrayT)
            params.append(Param(info.fg, info.type.elem if arr else info.type, arr))

        # Resolve the function's type
        if f.ret_type == VOID:
            ret_type: FgType = VOID
        elif f.ret_type is not None:
            ret_type = f.ret_type
        else:
            ret_type = None
            for t in self.ret_types:
                try:
                    ret_type = join_types(ret_type, t)
                except TypeError as e:
                    raise self.err(f"{f.py_name}() returns values of different types ({e})", f.node,
                                   "add a return annotation such as `-> float`")
            if ret_type is None:
                raise self.err(f"cannot infer the return type of {f.py_name}()", f.node,
                               "add a return annotation such as `-> int`")
            if isinstance(ret_type, ArrayT):
                raise self.err("functions cannot return arrays in Flowgorithm", f.node)
        if self.ret_var is not None:
            self.ret_var.type = ret_type

        decls = self.hoisted_declarations()
        body = header_comment + decls + body_ir
        return Function(f.fg_name, ret_type if isinstance(ret_type, str) else VOID,
                        self.ret_var.fg if self.ret_var else "", params, body)

    def make_return_var(self) -> VarInfo:
        """Pick the Flowgorithm return variable: a Python variable returned everywhere, else `result`."""
        returned: set[str] = set()
        all_simple = True
        for n in self.walk_function():
            if isinstance(n, ast.Return) and n.value is not None:
                v = n.value
                if (isinstance(v, ast.Name) and v.id not in self.vars and self.is_local(v.id)
                        and v.id not in self.list_names()):
                    returned.add(v.id)
                else:
                    all_simple = False
        if all_simple and len(returned) == 1:
            py = returned.pop()
            declared = self.f.ret_type  # the annotation, or None when the type is inferred
            info = VarInfo(py, self.ns.reserve(legalize(py)), declared or self.hints.get(py),
                           order=self.next_order(), declared=declared)
            self.vars[py] = info
            return info
        used = {n.id.lower() for n in self.walk_function() if isinstance(n, ast.Name)}
        base, cand, k = "result", "result", 1
        while cand in used:
            k += 1
            cand = f"{base}{k}"
        info = VarInfo(f"<return>", self.ns.reserve(cand), self.f.ret_type, order=self.next_order())
        self.vars[info.py] = info
        return info

    def list_names(self) -> set[str]:
        """Names the function binds to a list (they become arrays, never the return variable)."""
        return {t.id for n in self.walk_function() if isinstance(n, (ast.Assign, ast.AnnAssign))
                and n.value is not None and is_list_display(n.value)
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}

    def walk_function(self):
        for s in self.f.body:
            for n in ast.walk(s):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    what = "lambda expressions are" if isinstance(n, ast.Lambda) else "nested function definitions are"
                    raise self.err(f"{what} not supported", n)
                if isinstance(n, (ast.Yield, ast.YieldFrom)):
                    raise self.err("generators (yield) are not supported", n,
                                   "Flowgorithm functions return a single value; fill an array instead")
                yield n

    def hoisted_declarations(self) -> list:
        """Declare every scalar variable at the top, one Declare per type, plus constant assignments."""
        out: list = []
        by_type: dict[str, list[str]] = {}
        for info in sorted(self.vars.values(), key=lambda v: v.order):
            if info.is_param or info.is_array:
                continue
            if info.type is None:
                raise self.err(f"cannot infer the type of variable '{info.py}'", info.node or self.f.node,
                               f"annotate its first assignment, e.g. `{info.py}: int = ...`")
            if isinstance(info.type, ArrayT):  # pragma: no cover - arrays are declared in place
                continue
            by_type.setdefault(info.type, []).append(info.fg)
        for t, names in by_type.items():
            out.append(Declare(names, t))
        for info in sorted(self.vars.values(), key=lambda v: v.order):
            if info.is_const:
                out.append(Assign(info.fg, info.const_text))
        return out

    # --------------------------------------------------------------- comments
    def take_comments(self, start: int, end: int) -> tuple[list, bool]:
        """Comment shapes for comment lines in [start, end]; also reports an `fg: ignore` directive.

        Every directive that removes a statement was applied (and its line consumed) by the ignore
        pre-pass, so one found here has no statement to apply to.
        """
        items: list = []
        ignore = False
        for line in range(start, end + 1):
            if line in self.consumed or line not in self.m.comments:
                continue
            self.consumed.add(line)
            text = self.m.comments[line]
            d = parse_directive(text)
            if d is None:
                if self.b.comments_enabled and text.strip():
                    items.append(Comment(text.strip()))
                continue
            key, arg = d
            if key == "ignore":
                ignore = True
                self.warn_at("`# fg: ignore` is not followed by a statement of its block; nothing was "
                             "left out", line)
            elif key == "breakpoint":
                items.append(Breakpoint())
            elif key == "comment":
                items.append(Comment(arg))
            # name/title/about/author are program attributes (read by the builder); unknown keys
            # were reported when the module was loaded
        return items, ignore

    def else_line(self, s: ast.If, body_end: int, orelse_start: int) -> int:
        """Line of the `else:` keyword between a then-body and its else-body."""
        return find_else_line(self.m, s.col_offset, body_end + 1, orelse_start) or orelse_start

    # ------------------------------------------------------------------ blocks
    def block(self, stmts: list, start_line: int, end_line: Optional[int], indent: int = 0,
              moved: frozenset = frozenset()) -> list:
        """Convert a statement list. `indent` is the minimum column of comments that belong to it."""
        items = self.attach_comments(stmts, start_line, end_line, indent, moved)
        if self.loop_depth > 0 and contains_return(items):
            for st in ast_only(items):
                for n in ast.walk(st):
                    if isinstance(n, ast.Return):
                        raise self.err("return inside a loop is not supported", n,
                                       "Flowgorithm has no early return; use a flag variable in the "
                                       "loop condition and return after the loop")
        items = self.normalize_returns(items)
        out: list = []
        saved = self.pre, self.effects, self.conditional
        try:
            for i, item in enumerate(items):
                if not isinstance(item, ast.AST):  # Comment / Breakpoint shapes
                    out.append(item)
                    continue
                self.pre, self.effects, self.conditional = [], 0, 0
                if isinstance(item, ast.Return):
                    later = ast_only(items[i + 1:])
                    if later:
                        raise self.err("code after return is unreachable", later[0])
                    shapes = self.do_return(item)
                else:
                    shapes = self.stmt(item)
                out.extend(self.pre + shapes)  # what the statement's expressions need comes first
        finally:
            self.pre, self.effects, self.conditional = saved
        return out

    def take_pre(self) -> list:
        """The statements hoisted for the current statement, for a statement that places them itself."""
        pre, self.pre = self.pre, []
        return pre

    def hoist(self, shapes: list, node: ast.AST, what: str, mark: int) -> None:
        """Run `shapes` just before the current statement: an expression part that Flowgorithm cannot
        evaluate in place (an input(), a value used twice, ...). `mark` counts the side effects that
        were emitted in place before this part: they would now run after it."""
        if self.conditional:
            raise self.err(f"{what} on the right of `and` / `or` is not supported", node,
                           "Python evaluates it only sometimes; use nested if statements")
        if mark:
            raise self.err(f"{what} would have to run before a call that Python makes first", node,
                           "assign the result of that earlier call to a variable first")
        self.effects = mark
        self.pre.extend(shapes)

    def has_effects(self, node: ast.AST) -> bool:
        """Does evaluating `node` call something with side effects (a user function, input, random)?"""
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if self.b.resolve_callee(self.m, fn) is not None or isinstance(fn, ast.Name) and fn.id == "input":
                return True
            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                if self.b.module_alias_target(self.m, fn.value.id) == "random":
                    return True
            elif isinstance(fn, ast.Name) and (self.b.resolve_import(self.m, fn.id) or ("",))[0] == "random":
                return True
        return False

    def bool_as_number(self, node: ast.expr) -> ast.expr:
        """True/False as 1/0 (a Python bool is an int): an If shape before the statement sets a
        variable that the expression uses instead."""
        mark = self.effects
        cond = self.truthy(node)
        number = self.fresh_var("asNumber", INTEGER)
        self.hoist([If(cond, [Assign(number.fg, "1")], [Assign(number.fg, "0")])], node,
                   "a Boolean used as a number", mark)
        return ast.copy_location(ast.Name(id=number.py, ctx=ast.Load()), node)

    def hoist_value(self, node: ast.expr, base: str, what: str) -> ast.expr:
        """Evaluate `node` once, into a fresh variable, before the statement; returns a Name for it."""
        mark = self.effects
        t = self.infer(node)
        if t is None or isinstance(t, ArrayT):
            raise self.err(f"cannot infer the type of {what}", node, "assign it to a variable first")
        tmp = self.fresh_var(base, t)
        self.hoist([Assign(tmp.fg, self.text(node))], node, what, mark)
        return ast.copy_location(ast.Name(id=tmp.py, ctx=ast.Load()), node)

    def attach_comments(self, stmts: list, start_line: int, end_line: Optional[int], indent: int,
                        moved: frozenset = frozenset()) -> list:
        """Interleave Comment/Breakpoint shapes with the statements they precede (source order).

        The comments indented under a compound statement after its last line stay with it (its
        inner block picks them up as trailing comments). `moved` holds the statements that
        normalize_returns() appended to this block: they come with their comments already attached
        and follow the block's own trailing comments.
        """
        items: list = []
        prev_end = start_line - 1
        closed = False
        for st in stmts:
            if not isinstance(st, ast.AST) or id(st) in moved:
                if not closed:
                    items.extend(self.trailing_comments(prev_end, end_line, indent))
                    closed = True
                items.append(st)
                continue
            found, _ = self.take_comments(prev_end + 1, header_end(self.m, st))
            items.extend(found)
            items.append(st)
            prev_end = trailing_end(self.m, st)
        if not closed:
            items.extend(self.trailing_comments(prev_end, end_line, indent))
        return items

    def trailing_comments(self, prev_end: int, end_line: Optional[int], indent: int) -> list:
        """Comments after a block's last statement: up to end_line, plus the comment lines indented
        like the block's statements (lines of statements left out by `# fg: ignore` are skipped)."""
        last = end_line or 0
        ln = prev_end + 1
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
        if last < prev_end + 1:
            return []
        return self.take_comments(prev_end + 1, last)[0]

    def normalize_returns(self, items: list) -> list:
        """Flowgorithm has no early return: statements that follow an if-chain containing a return
        are moved into every branch that does not itself return on all paths.

        Builds new If nodes rather than mutating the AST, so a function can be converted more
        than once (several programs in one directory share modules).
        """
        out: list = []
        for i, st in enumerate(items):
            rest = items[i + 1:]
            if isinstance(st, ast.If) and ast_only(rest) and (may_return(st.body) or may_return(st.orelse)):
                b_all, e_all = ends_with_return(st.body), ends_with_return(st.orelse)
                if b_all and e_all:
                    self.warn("unreachable code after if/else that returns in both branches", ast_only(rest)[0])
                    out.append(st)
                    return out
                body = list(st.body) if b_all else list(st.body) + rest
                orelse = list(st.orelse) if e_all else list(st.orelse) + rest
                out.append(self.if_with(st, body, orelse, rest))
                return out
            out.append(st)
        return out

    @staticmethod
    def if_with(orig: ast.If, body: list, orelse: list, rest: list) -> ast.If:
        """A copy of `orig` whose branches got the statements `rest` appended (see normalize_returns)."""
        new = ast.If(test=orig.test, body=body, orelse=orelse)
        ast.copy_location(new, orig)
        new._moved = frozenset(id(x) for x in ast_only(rest)) | getattr(orig, "_moved", frozenset())
        new._orig_end = getattr(orig, "_orig_end", orig.end_lineno or orig.lineno)
        new.end_lineno = max([new._orig_end] + [x.end_lineno or x.lineno for x in ast_only(rest)])
        return new

    def stmt(self, s: ast.stmt) -> list:
        handler = getattr(self, "s_" + type(s).__name__, None)
        if handler is None:
            raise self.err(f"unsupported statement: {type(s).__name__}", s)
        return handler(s)

    # ------------------------------------------------------------- statements
    def s_Pass(self, s: ast.Pass) -> list:
        return []

    def s_Import(self, s: ast.Import) -> list:
        return []

    def s_ImportFrom(self, s: ast.ImportFrom) -> list:
        return []

    def s_Assert(self, s: ast.Assert) -> list:
        self.warn("assert statement skipped (not representable in Flowgorithm)", s)
        return []

    def s_Global(self, s: ast.Global) -> list:
        raise self.err("global variables do not exist in Flowgorithm", s,
                       "pass the value as a parameter, or make it a module-level literal constant")

    s_Nonlocal = s_Global

    def s_Break(self, s: ast.Break) -> list:
        raise self.err("break is only supported as `while True: ... if cond: break` "
                       "(first or last statement of the loop)", s)

    def s_Continue(self, s: ast.Continue) -> list:
        raise self.err("continue is not supported", s, "wrap the rest of the loop body in an if")

    def s_Return(self, s: ast.Return) -> list:  # pragma: no cover - handled in block()
        return self.do_return(s)

    def s_FunctionDef(self, s: ast.FunctionDef) -> list:
        raise self.err("nested function definitions are not supported", s)

    def s_ClassDef(self, s: ast.ClassDef) -> list:
        raise self.err("classes are not supported; Flowgorithm only has functions", s)

    def s_Try(self, s: ast.Try) -> list:
        raise self.err("try/except is not supported", s,
                       "Flowgorithm has no exceptions; validate with if/while instead")

    def s_With(self, s: ast.With) -> list:
        raise self.err("with statements are not supported", s)

    def s_Raise(self, s: ast.Raise) -> list:
        raise self.err("raise is not supported", s)

    def s_Delete(self, s: ast.Delete) -> list:
        raise self.err("del is not supported", s)

    def do_return(self, s: ast.Return) -> list:
        if self.loop_depth > 0:
            raise self.err("return inside a loop is not supported", s)
        if isinstance(s.value, ast.Constant) and s.value.value is None:
            s = ast.copy_location(ast.Return(value=None), s)
        if s.value is None:
            if self.ret_var is not None:
                raise self.err("return without a value in a function that returns a value", s)
            return []
        if self.f.is_main:
            raise self.err("main() cannot return a value", s)
        if self.ret_var is None:  # pragma: no cover - builder marks value returns
            raise self.err("unexpected return value", s)
        t = self.infer(s.value)
        declared = self.f.ret_type if isinstance(self.f.ret_type, str) and self.f.ret_type != VOID else None
        if declared is not None and t is not None and not assignable(declared, t):
            raise self.err(f"{self.f.py_name}() is annotated `-> {py_type(declared)}` but returns "
                           f"{py_type(t)}", s.value, "change the annotation or convert the value")
        text = self.text(s.value)
        self.ret_types.append(t)
        if isinstance(s.value, ast.Name) and self.var_info(s.value.id) is self.ret_var:
            return []
        return [Assign(self.ret_var.fg, text)]

    def s_Expr(self, s: ast.Expr) -> list:
        v = s.value
        if isinstance(v, ast.Call):
            fn = v.func
            if isinstance(fn, ast.Name) and self.b.resolve_callee(self.m, fn) is None:
                if fn.id == "print":
                    return self.s_print(v)
                if fn.id == "breakpoint":
                    return [Breakpoint()]
                if fn.id == "input":
                    prompt = v.args[0] if v.args else None
                    out = self.prompt_output(prompt)
                    pause = self.fresh_var("pause", STRING)
                    out.append(Input(pause.fg))
                    return out
            fi = self.b.resolve_callee(self.m, fn)
            if fi is not None:
                return [Call(self.user_call(v, fi))]
            if isinstance(fn, ast.Attribute):
                raise self.err(f"unsupported method call '.{fn.attr}()'", s,
                               "Flowgorithm has no methods; arrays have a fixed size and strings only "
                               "support Len, Char, & and comparisons")
            raise self.err("this call has no Flowgorithm equivalent", s)
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return [Comment(v.value.strip())] if self.b.comments_enabled else []
        if isinstance(v, (ast.Yield, ast.YieldFrom)):
            raise self.err("generators (yield) are not supported", s,
                           "Flowgorithm functions return a single value; fill an array instead")
        raise self.err("expression statement has no effect", s)

    def s_Assign(self, s: ast.Assign) -> list:
        if len(s.targets) > 1:  # a = b = value
            out = self.assign_to(s.targets[0], s.value, s)
            for t in s.targets[1:]:
                out += self.assign_to(t, ast.copy_location(self.as_load(s.targets[0]), s), s)
            return out
        return self.assign_to(s.targets[0], s.value, s)

    def s_AnnAssign(self, s: ast.AnnAssign) -> list:
        t = self.annotation_type(s.annotation)
        if not isinstance(s.target, ast.Name):
            raise self.err("annotated assignment target must be a plain variable", s)
        if s.value is None:
            if isinstance(t, ArrayT):
                raise self.err("an array needs a size: write `xs: list[int] = [0] * n`", s)
            self.var_assign(s.target.id, t, s)
            return []
        return self.assign_to(s.target, s.value, s, ann=t)

    def s_AugAssign(self, s: ast.AugAssign) -> list:
        target = s.target
        if (isinstance(s.op, (ast.Add, ast.Sub)) and self.infer(s.value) == BOOLEAN
                and is_numeric(self.infer(self.as_load(target)))):
            # `count += x > 0` counts: If x > 0 then count = count + 1
            cond = self.truthy(s.value)
            one = ast.copy_location(ast.Constant(value=1), s.value)
            return [If(cond, self.s_AugAssign(ast.copy_location(
                ast.AugAssign(target=target, op=s.op, value=one), s)), [])]
        if isinstance(target, ast.Subscript) and has_call(target.slice):
            # `tally[random.randint(1, 6)] += 1` reads and writes the same element: one index
            index = self.hoist_value(target.slice, "pos", "the index")
            target = ast.copy_location(ast.Subscript(value=target.value, slice=index, ctx=ast.Store()), target)
        binop = ast.copy_location(ast.BinOp(left=self.as_load(target), op=s.op, right=s.value), s)
        ast.fix_missing_locations(binop)
        return self.assign_to(target, binop, s)

    @staticmethod
    def as_load(target: ast.expr) -> ast.expr:
        node = copy.deepcopy(target)
        for n in ast.walk(node):
            if hasattr(n, "ctx"):
                n.ctx = ast.Load()
        return node

    def s_If(self, s: ast.If) -> list:
        cond = self.truthy(s.test)
        # statements appended by normalize_returns() are not part of this if's source range
        moved = getattr(s, "_moved", frozenset())
        orig_end = getattr(s, "_orig_end", s.end_lineno)
        body_own = [x for x in ast_only(s.body) if id(x) not in moved]
        orelse_own = [x for x in ast_only(s.orelse) if id(x) not in moved]
        head = header_end(self.m, s)
        if orelse_own:  # a real else (or elif) branch
            body_end = body_own[-1].end_lineno if body_own else head
            else_line = self.else_line(s, body_end, orelse_own[0].lineno)
            then_end, else_start = else_line - 1, else_line
        else:
            then_end, else_start = orig_end, orig_end + 1
        before = self.stale_copy()
        then = self.block(s.body, head + 1, then_end, s.col_offset + 1, moved)
        after_then, self.stale = self.stale, before
        else_ = self.block(s.orelse, else_start, orig_end, s.col_offset + 1, moved) if s.orelse else []
        self.stale_merge(after_then)
        return [If(cond, then, else_)]

    def s_While(self, s: ast.While) -> list:
        if s.orelse:
            raise self.err("while ... else is not supported", s)
        body = ast_only(s.body)  # statements marked `# fg: ignore` are already gone
        head = header_end(self.m, s)
        if is_true_literal(s.test):
            if body and is_break_if(body[-1]) and not has_break_or_continue(body[:-1]):
                # Do loop: convert the body first so variables it defines are known to the condition
                brk = body[-1]
                inner = self.loop_body(s, body[:-1], head + 1, brk.lineno - 1, s.col_offset + 1)
                tail, _ = self.take_comments(brk.lineno, trailing_end(self.m, s))
                self.check_compare_types(brk.test)
                cond = self.negate(brk.test)
                return [Do(cond, inner + tail + self.take_pre())]  # the condition is tested last
            if body and is_break_if(body[0]) and not has_break_or_continue(body[1:]):
                brk = body[0]
                self.check_compare_types(brk.test)
                cond = self.negate(brk.test)
                pre = self.take_pre()
                brk_end = trailing_end(self.m, brk)
                lead, _ = self.take_comments(head + 1, brk_end)
                before = self.stale_copy()
                inner = self.loop_body(s, body[1:], brk_end + 1, s.end_lineno, s.col_offset + 1)
                self.stale_merge(before)
                return pre + [While(cond, lead + inner + copy.deepcopy(pre))]
            raise self.err("`while True` needs a single `if cond: break` as the first statement "
                           "(-> While loop) or the last statement (-> Do loop) of its body", s)
        if has_break_or_continue(body):
            raise self.err("break/continue inside a while loop is not supported", s,
                           "fold the exit condition into the loop condition")
        cond = self.truthy(s.test)
        pre = self.take_pre()  # what the condition needs runs before the loop and after each pass
        before = self.stale_copy()
        inner = self.loop_body(s, s.body, head + 1, s.end_lineno, s.col_offset + 1)
        self.stale_merge(before)
        return pre + [While(cond, inner + copy.deepcopy(pre))]

    def check_compare_types(self, test: ast.expr) -> None:
        if isinstance(test, ast.Compare):
            for left, right in zip([test.left] + list(test.comparators), test.comparators):
                lt, rt = self.infer(left), self.infer(right)
                if lt is not None and rt is not None and not self.compatible(lt, rt):
                    raise self.err(f"comparing {type_name(lt)} with {type_name(rt)}", test)

    def loop_body(self, loop: ast.stmt, stmts: list, start: int, end: Optional[int], indent: int = 0) -> list:
        self.loop_depth += 1
        self.loop_stack.append(loop)
        try:
            return self.block(stmts, start, end, indent)
        finally:
            self.loop_stack.pop()
            self.loop_depth -= 1

    def stale_copy(self) -> dict[str, set[int]]:
        return {k: set(v) for k, v in self.stale.items()}

    def stale_merge(self, other: dict[str, set[int]]) -> None:
        """Join two paths (if branches, or a loop body that may not run): stale on either is stale."""
        for k, v in other.items():
            self.stale.setdefault(k, set()).update(v)

    def read_names(self) -> set[str]:
        """Names whose value the function reads somewhere (`x += 1` reads x too)."""
        if self.reads is None:
            self.reads = set()
            for st in ast_only(self.f.body):
                for n in ast.walk(st):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                        self.reads.add(n.id)
                    elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                        self.reads.add(n.target.id)
        return self.reads

    def counter_is_direct(self, name: str, s: ast.For) -> bool:
        """Can the For shape count with the Python loop variable itself? Flowgorithm's For uses its
        variable as the counter, so not when the body assigns it (that would change the iteration,
        nested loops included), when a later read needs Python's last value (Flowgorithm's counter
        ends past it), when the variable is not an Integer, or when an enclosing loop reads it
        outside this loop (a later pass of that loop would see the counter's final value)."""
        if id(s) in self.hidden_loops or name in assigned_names(s.body):
            return False
        hint, info = self.hints.get(name), self.var_info(name)
        if hint not in (None, INTEGER) or (info is not None and info.type not in (None, INTEGER)):
            return False
        return not any(reads_name(outer, name, s) for outer in self.loop_stack)

    def s_For(self, s: ast.For) -> list:
        if s.orelse:
            raise self.err("for ... else is not supported", s)
        if has_break_or_continue(s.body):
            raise self.err("break/continue inside a for loop is not supported", s,
                           "use a while loop with the exit condition in its test")
        it, tgt = s.iter, s.target
        is_range = (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "range"
                    and self.b.resolve_callee(self.m, it.func) is None)
        # The bounds and the sequence are evaluated before the loop variables are bound.
        if is_range:
            if not isinstance(tgt, ast.Name):
                raise self.err("for loop over range() needs a simple variable", s)
            if it.keywords:
                raise self.err("range() with keyword arguments is not supported", s)
            start, end, direction, step = self.range_bounds(it, s)
            counter_name, elem_name, seq_info = tgt.id, None, None
        else:
            if (isinstance(it, ast.Call) and isinstance(it.func, ast.Name) and it.func.id == "enumerate"
                    and len(it.args) == 1 and isinstance(tgt, ast.Tuple) and len(tgt.elts) == 2
                    and all(isinstance(e, ast.Name) for e in tgt.elts)):
                counter_name, elem_name, seq = tgt.elts[0].id, tgt.elts[1].id, it.args[0]
            elif isinstance(tgt, ast.Name):
                counter_name, elem_name, seq = None, tgt.id, it
            else:
                raise self.err("unsupported for loop", s,
                               "supported: for i in range(...), for x in xs, for i, x in enumerate(xs)")
            if not isinstance(seq, ast.Name):
                raise self.err("for loops can only iterate over range(), a list variable or a string variable", s)
            seq_info = self.lookup(seq)
            if not (isinstance(seq_info.type, ArrayT) or seq_info.type == STRING):
                raise self.err(f"cannot iterate over '{seq.id}' of type {type_name(seq_info.type)}", s)
            start, direction, step = "0", "inc", "1"
            end = f"{'Size' if isinstance(seq_info.type, ArrayT) else 'Len'}({seq_info.fg}) - 1"

        before = self.stale_copy()
        prologue: list = []
        direct = False
        if counter_name is None:  # for x in xs: count with an index of its own
            counter = self.fresh_var(legalize(elem_name) + "Index", INTEGER)
        elif self.counter_is_direct(counter_name, s):
            counter = self.var_assign(counter_name, INTEGER, s)
            self.loop_counters.append((counter, s))
            direct = True
        elif counter_name in self.read_names():
            # count with a hidden variable; the Python name gets its value at the top of every pass
            counter = self.fresh_var(legalize(counter_name) + "Counter", INTEGER)
            prologue.append(Assign(self.var_assign(counter_name, INTEGER, s).fg, counter.fg))
        else:  # never read (`for _ in range(3)`): a counter of its own will do
            counter = self.fresh_var(legalize(counter_name) + "Counter", INTEGER)
        if elem_name is not None and elem_name in self.read_names():
            if isinstance(seq_info.type, ArrayT):
                elem_text, elem_type = f"{seq_info.fg}[{counter.fg}]", seq_info.type.elem
            else:
                elem_text, elem_type = f"Char({seq_info.fg}, {counter.fg})", STRING
            prologue.append(Assign(self.var_assign(elem_name, elem_type, s).fg, elem_text))
        body = prologue + self.loop_body(s, s.body, header_end(self.m, s) + 1, s.end_lineno, s.col_offset + 1)
        self.stale_merge(before)  # the body may not run at all
        if direct:
            self.stale[counter_name] = {id(s)}
        return [For(counter.fg, start, end, direction, step, body)]

    def range_bounds(self, call: ast.Call, s: ast.For) -> tuple[str, str, str, str]:
        args = call.args
        if len(args) == 1:
            start_node, stop_node, step_node = None, args[0], None
        elif len(args) == 2:
            start_node, stop_node, step_node = args[0], args[1], None
        elif len(args) == 3:
            start_node, stop_node, step_node = args
        else:
            raise self.err("range() takes 1 to 3 arguments", call)
        direction, step = "inc", "1"
        if step_node is not None:
            sv = self.int_literal(step_node)  # a literal or a module constant: its sign is known
            if sv is None and isinstance(step_node, ast.UnaryOp) and isinstance(step_node.op, ast.USub):
                direction, step = "dec", self.text(step_node.operand)
            elif sv is None:
                self.warn("non-literal range step assumed positive (write -step for a descending loop)", step_node)
                step = self.text(step_node)
            elif sv == 0:
                raise self.err("range() step must not be zero", step_node)
            elif sv < 0:  # Flowgorithm's step is positive: `-STEP` keeps a constant's name
                direction = "dec"
                step = str(-sv) if self.literal_int(step_node) is not None else f"-{self.sub(step_node, P_UNARY)}"
            else:
                step = self.text(step_node)
        start = self.text(start_node) if start_node is not None else "0"
        if not is_numeric(self.infer(stop_node)) and self.infer(stop_node) is not None:
            raise self.err("range() bound must be an integer expression", stop_node)
        end = self.minus_one(stop_node) if direction == "inc" else self.plus_one(stop_node)
        return start, end, direction, step

    @staticmethod
    def literal_int(node: ast.expr) -> Optional[int]:
        """The value of an integer literal (`3`, `-3`), else None."""
        if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub)
                and isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int)
                and not isinstance(node.operand.value, bool)):
            return -node.operand.value
        return None

    def int_literal(self, node: ast.expr) -> Optional[int]:
        """The value of an integer literal or of an integer module constant (to decide things such
        as a step's sign; the text keeps a constant's name)."""
        v = self.literal_int(node)
        if v is None and isinstance(node, (ast.Name, ast.Attribute)):
            const = self.module_constant(node)
            if const is not None and const[1] == INTEGER:
                try:
                    return int(const[2])
                except ValueError:  # pragma: no cover
                    return None
        return v

    def add_literal(self, node: ast.expr, k: int) -> str:
        """Text of `node + k` with literal folding (k may be negative)."""
        if k == 0:
            return self.text(node)
        v = self.literal_int(node)
        if v is not None:
            return str(v + k)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            c = self.literal_int(node.right)
            if c is not None:
                total = (c if isinstance(node.op, ast.Add) else -c) + k
                return self.add_literal(node.left, total)
        left = self.sub(node, P_ADD)
        return f"{left} + {k}" if k > 0 else f"{left} - {-k}"

    def minus_one(self, node: ast.expr) -> str:
        return self.add_literal(node, -1)

    def plus_one(self, node: ast.expr) -> str:
        return self.add_literal(node, 1)

    def minus_expr(self, b: ast.expr, a: ast.expr, k: int = 0) -> str:
        """Text of `b - a + k` with literal folding."""
        av = self.literal_int(a)
        if av is not None:
            return self.add_literal(b, k - av)
        bv = self.literal_int(b)
        if bv is not None and av is not None:  # pragma: no cover
            return str(bv - av + k)
        base = f"{self.sub(b, P_ADD)} - {self.sub(a, P_ADD, 'right')}"
        if k:
            base += f" + {k}" if k > 0 else f" - {-k}"
        return base

    def negate(self, test: ast.expr) -> str:
        return self.negate_expr(test)[0]

    def negate_expr(self, test: ast.expr) -> tuple[str, int]:
        """Flowgorithm text for `not <test>`, simplified where possible (`n > 0` -> `n <= 0`)."""
        if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
            return self.truthy_expr(test.operand)
        if isinstance(test, ast.Compare) and len(test.ops) == 1 and type(test.ops[0]) in FLIP_COMPARE:
            self.check_compare_types(test)
            op = FLIP_COMPARE[type(test.ops[0])]
            return f"{self.sub(test.left, P_REL)} {op} {self.sub(test.comparators[0], P_REL, 'right')}", P_REL
        t = self.infer(test)
        if is_numeric(t):
            return f"{self.sub(test, P_REL)} == 0", P_REL
        if t == STRING:
            return f'{self.sub(test, P_REL)} == ""', P_REL
        if isinstance(t, ArrayT):
            return f"Size({self.text(test)}) == 0", P_REL
        text, p = self.truthy_expr(test)
        return "not " + (f"({text})" if p < P_UNARY else text), P_UNARY

    def truthy(self, node: ast.expr) -> str:
        """Flowgorithm Boolean text for a Python truth test (`if n:` -> `n != 0`)."""
        return self.truthy_expr(node)[0]

    def truthy_expr(self, node: ast.expr) -> tuple[str, int]:
        if isinstance(node, ast.BoolOp):
            word, p = ("and", P_AND) if isinstance(node.op, ast.And) else ("or", P_OR)
            parts = []
            for k, v in enumerate(node.values):
                self.conditional += k > 0
                try:
                    t, vp = self.truthy_expr(v)
                finally:
                    self.conditional -= k > 0
                parts.append(f"({t})" if vp < p else t)
            return f" {word} ".join(parts), p
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self.negate_expr(node.operand)
        t = self.infer(node)
        if t == BOOLEAN or t is None:
            return self.expr(node)
        if is_numeric(t):
            return f"{self.sub(node, P_REL)} != 0", P_REL
        if t == STRING:
            return f'{self.sub(node, P_REL)} != ""', P_REL
        if isinstance(t, ArrayT):
            return f"Size({self.text(node)}) != 0", P_REL
        return self.expr(node)  # pragma: no cover

    # ----------------------------------------------------------- assignments
    def assign_to(self, target: ast.expr, value: ast.expr, node: ast.stmt, ann: FgType = None) -> list:
        if isinstance(target, ast.Name):
            inp = self.match_input(value)
            if inp is not None:
                prompt, t = inp
                if ann is not None:
                    if isinstance(ann, ArrayT):
                        raise self.err("cannot read an array with input()", node)
                    t = ann
                out = self.prompt_output(prompt)
                var = self.var_assign(target.id, t, node)
                out.append(Input(var.fg))
                return out
            arr = self.match_list_create(value, node)
            if arr is not None:
                return self.declare_array(target.id, arr, node, ann)
            t = self.infer(value)
            if isinstance(t, ArrayT) or isinstance(ann, ArrayT):
                raise self.err("arrays can only be created with `[value] * size` or a list literal", node)
            text = self.text(value)
            if ann is not None:
                if t is not None and not assignable(ann, t):
                    raise self.err(f"'{target.id}' is annotated {py_type(ann)} but assigned {py_type(t)}",
                                   node, self.annotation_hint(ann, t))
                t = ann
            var = self.var_assign(target.id, t, node, declared=ann)
            return [Assign(var.fg, text)]
        if isinstance(target, ast.Subscript):
            tgt_text, info = self.index_target(target)
            inp = self.match_input(value)
            if inp is not None:
                prompt, t = inp
                self.check_element_store(info, t, node)
                return self.prompt_output(prompt) + [Input(tgt_text)]
            t = self.infer(value)
            if t is not None:
                self.check_element_store(info, t, node)
            if isinstance(node, ast.AugAssign) and has_call(target.slice):
                raise self.err("the index expression would be evaluated twice", node,
                               "assign the index to a variable first")
            return [Assign(tgt_text, self.text(value))]
        if isinstance(target, (ast.Tuple, ast.List)):
            return self.tuple_assign(target, value, node)
        raise self.err("unsupported assignment target", node)

    @staticmethod
    def compatible(declared: FgType, value: FgType) -> bool:
        """Can the two types be compared (numbers mix freely)?"""
        if declared == value:
            return True
        return is_numeric(declared) and is_numeric(value)

    @staticmethod
    def annotation_hint(declared: FgType, value: FgType) -> str:
        if declared == INTEGER and value == REAL:
            return "Flowgorithm would cut off the fraction: annotate it as float, or convert with int(...)"
        return ""

    def check_element_store(self, info: VarInfo, t: FgType, node: ast.AST) -> None:
        """Storing a `t` into an element of array `info`: an inferred Integer array widens to Real
        (and the function is converted again with the wider type); anything else must fit."""
        elem = info.type.elem
        if assignable(elem, t):
            return
        if elem == INTEGER and t == REAL and info.declared is None and not info.is_param:
            info.type = ArrayT(REAL)
            self.widened = True
            return
        raise self.err(f"cannot store a {py_type(t)} in '{info.py}', a {py_type(info.type)}", node,
                       self.annotation_hint(elem, t))

    def tuple_assign(self, target: ast.expr, value: ast.expr, node: ast.stmt) -> list:
        if not isinstance(value, (ast.Tuple, ast.List)) or len(value.elts) != len(target.elts):
            raise self.err("tuple unpacking is only supported as `a, b = x, y`", node)
        left_names: set[str] = set()
        for t in target.elts:
            base = t.value if isinstance(t, ast.Subscript) else t
            if isinstance(base, ast.Name):
                left_names.add(base.id)
        right_names = {n.id for v in value.elts for n in ast.walk(v) if isinstance(n, ast.Name)}
        out: list = []
        if left_names & right_names:  # swap-like: evaluate all right sides first
            temps = []
            for v in value.elts:
                tmp = self.fresh_var("temp", self.infer(v))
                if tmp.type is None:
                    raise self.err("cannot infer the type of a swapped value", node)
                out.append(Assign(tmp.fg, self.text(v)))
                temps.append(tmp)
            for t, tmp in zip(target.elts, temps):
                out += self.assign_to(t, ast.copy_location(ast.Name(id=tmp.py, ctx=ast.Load()), node), node)
            return out
        for t, v in zip(target.elts, value.elts):
            out += self.assign_to(t, v, node)
        return out

    def prompt_output(self, prompt: Optional[ast.expr]) -> list:
        """The Output shape(s) that show an input() prompt (none for `input()` / `input("")`)."""
        if prompt is None or const_str(prompt) == "":
            return []
        return self.output_items([("expr", prompt)], True)

    def match_input(self, value: ast.expr) -> Optional[tuple[Optional[ast.expr], str]]:
        """Recognise input(p), int(input(p)), float(input(p)), str(input(p)), optionally .strip()."""
        node = value
        cast = None
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in ("int", "float", "str") and len(node.args) == 1 and not node.keywords
                and self.b.resolve_callee(self.m, node.func) is None):
            cast = node.func.id
            node = node.args[0]
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "strip"
                and not node.args):
            node = node.func.value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "input"
                and len(node.args) <= 1 and not node.keywords
                and self.b.resolve_callee(self.m, node.func) is None):
            prompt = node.args[0] if node.args else None
            return prompt, {"int": INTEGER, "float": REAL, "str": STRING, None: STRING}[cast]
        return None

    def match_list_create(self, value: ast.expr, node: ast.stmt):
        """`[x] * n`, `n * [x]` -> ('fill', x, n); `[a, b, c]` -> ('literal', elts)."""
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Mult):
            for lst, n in ((value.left, value.right), (value.right, value.left)):
                if isinstance(lst, ast.List):
                    if len(lst.elts) != 1:
                        raise self.err("array creation needs exactly one fill value: `[0] * n`", node)
                    return ("fill", lst.elts[0], n, lst is value.left)
        if isinstance(value, ast.List):
            if not value.elts:
                raise self.err("empty lists are not supported; Flowgorithm arrays have a fixed size", node,
                               "create it with `[0] * n`")
            return ("literal", value.elts, None, True)
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "list":
            raise self.err("list() is not supported; create arrays with `[0] * n`", node)
        return None

    def declare_array(self, py_name: str, spec, node: ast.stmt, ann: FgType) -> list:
        kind, a, n = spec[:3]
        if py_name in self.vars:
            raise self.err(f"'{py_name}' is already defined; arrays cannot be re-created", node)
        if any(is_list_display(e) for e in ([a] if kind == "fill" else a)):
            raise self.err("nested lists are not supported (Flowgorithm arrays are 1-D)", node,
                           "use one array per row, or one array of rows * columns elements")
        if kind == "fill":
            if has_call(a) and spec[3]:  # `[random.randint(1, 6)] * n` repeats ONE value
                a = self.hoist_value(a, "fill", "the fill value")
            elem_type = self.infer(a)
            size_t = self.infer(n)
            if size_t is not None and size_t != INTEGER:
                raise self.err("array size must be an integer expression", n)
            size = self.text(n)
            if has_call(a):  # `n * [f()]`: the size comes first
                a = self.hoist_value(a, "fill", "the fill value")
        else:
            elem_type = None
            for e in a:
                try:
                    elem_type = join_types(elem_type, self.infer(e))
                except TypeError as ex:
                    raise self.err(f"list elements have different types ({ex})", node)
            size = str(len(a))
        if isinstance(ann, ArrayT):
            if elem_type is not None and not assignable(ann.elem, elem_type):
                raise self.err(f"'{py_name}' is annotated {py_type(ann)} but its elements are "
                               f"{py_type(elem_type)}", node, self.annotation_hint(ann.elem, elem_type))
            elem_type = ann.elem
        elif ann is not None:
            raise self.err(f"'{py_name}' is annotated {py_type(ann)} but assigned a list", node)
        else:
            hint = self.hints.get(py_name)  # a later element store widened the array
            if isinstance(hint, ArrayT) and isinstance(elem_type, str):
                try:
                    elem_type = join_types(elem_type, hint.elem)
                except TypeError:  # pragma: no cover - stores are type-checked
                    pass
        if elem_type is None or isinstance(elem_type, ArrayT):
            raise self.err(f"cannot infer the element type of list '{py_name}'", node,
                           f"annotate it: `{py_name}: list[int] = ...`")
        if self.loop_depth > 0:
            self.warn(f"array '{py_name}' is created inside a loop; Flowgorithm re-declares it on every "
                      f"iteration", node)
        fg = self.ns.reserve(legalize(py_name))
        self.vars[py_name] = VarInfo(py_name, fg, ArrayT(elem_type), is_array=True, order=self.next_order(),
                                     declared=ann, node=node)
        out: list = [Declare([fg], elem_type, True, size)]
        if kind == "fill":
            v = a.value if isinstance(a, ast.Constant) else object()
            if type(v) is bool:
                is_default = elem_type == BOOLEAN and v is False
            else:
                is_default = v in DEFAULT_VALUES[elem_type]
            if not is_default:  # Flowgorithm arrays start out as 0 / "" / false
                idx = self.fresh_var("idx", INTEGER)
                out.append(For(idx.fg, "0", f"{size} - 1", "inc", "1", [Assign(f"{fg}[{idx.fg}]", self.text(a))]))
        else:
            for i, e in enumerate(a):
                out.append(Assign(f"{fg}[{i}]", self.text(e)))
        return out

    def index_target(self, sub: ast.Subscript) -> tuple[str, VarInfo]:
        if not isinstance(sub.value, ast.Name):
            raise self.err("only variables can be indexed", sub)
        info = self.lookup(sub.value)
        if not isinstance(info.type, ArrayT):
            if info.type == STRING:
                raise self.err("strings cannot be modified in place", sub,
                               "build a new string with concatenation")
            raise self.err(f"'{sub.value.id}' is not an array", sub)
        return f"{info.fg}[{self.index_text(sub, info)}]", info

    def index_text(self, sub: ast.Subscript, info: VarInfo) -> str:
        idx = sub.slice
        if isinstance(idx, ast.Slice):
            raise self.err("slicing is not supported", sub)
        k = self.int_literal(idx)
        size = f"Size({info.fg})" if isinstance(info.type, ArrayT) else f"Len({info.fg})"
        if k is not None and k < 0:
            return f"{size} - {-k}"
        if isinstance(idx, ast.UnaryOp) and isinstance(idx.op, ast.USub) and k is None:
            return f"{size} - {self.sub(idx.operand, P_ADD, 'right')}"
        t = self.infer(idx)
        if t is not None and t != INTEGER:
            raise self.err("array index must be an integer", idx)
        return self.text(idx)

    # ---------------------------------------------------------------- output
    def s_print(self, call: ast.Call) -> list:
        sep, end = " ", "\n"
        for kw in call.keywords:
            if kw.arg == "sep":
                sep = const_str(kw.value)
                if sep is None:
                    raise self.err("print(sep=...) must be a string literal", kw.value)
            elif kw.arg == "end":
                end = const_str(kw.value)
                if end is None:
                    raise self.err("print(end=...) must be a string literal", kw.value)
            elif kw.arg in ("file", "flush"):
                self.warn(f"print({kw.arg}=...) ignored", call)
            else:
                raise self.err(f"unsupported print argument '{kw.arg}'", call)
        items: list = []
        for i, a in enumerate(call.args):
            if isinstance(a, ast.Starred):
                raise self.err("print(*args) is not supported", a)
            if i and sep:
                items.append(("lit", sep))
            items.append(("expr", a))
        trailing_newline = end.endswith("\n")
        end_text = end[:-1] if trailing_newline else end
        if end_text:
            items.append(("lit", end_text))
        return self.output_items(items, trailing_newline)

    def output_items(self, items: list, newline: bool) -> list:
        """Turn a list of ('lit', str) / ('expr', node) parts into Output shapes, one per text line."""
        lines: list[list] = [[]]
        for kind, val in items:
            if kind == "expr":
                s = const_str(val)
                if s is not None:
                    kind, val = "lit", s
                elif isinstance(val, ast.JoinedStr):  # f-string: expand literal pieces
                    for part in val.values:
                        s = const_str(part)
                        if s is not None:
                            self._split_lit(lines, s)
                        else:
                            lines[-1].append(("expr", self.format_value(part)))
                    continue
            if kind == "lit":
                self._split_lit(lines, val)
            else:
                lines[-1].append(("expr", val))
        out: list = []
        for j, line in enumerate(lines):
            last = j == len(lines) - 1
            nl = newline if last else True
            if not line:
                if last and not nl:
                    continue
                out.append(Output('""', nl))
            else:
                out.append(Output(self.concat(line), nl))
        return out

    @staticmethod
    def _split_lit(lines: list[list], text: str) -> None:
        for j, chunk in enumerate(text.split("\n")):
            if j:
                lines.append([])
            if chunk:
                lines[-1].append(("lit", chunk))

    def concat(self, parts: list) -> str:
        """Join literal/expression parts with Flowgorithm's & operator."""
        merged: list = []
        for kind, val in parts:
            if kind == "lit" and merged and merged[-1][0] == "lit":
                merged[-1] = ("lit", merged[-1][1] + val)
            else:
                merged.append((kind, val))
        texts = []
        for kind, val in merged:
            if kind == "lit":
                t, p = self.str_lit(val)
            else:
                val = self.strip_str_call(val)
                if isinstance(self.infer(val), ArrayT):
                    raise self.err("a whole array cannot be output; print its elements in a loop", val)
                t, p = self.expr(val)
            texts.append(f"({t})" if p < P_CAT else t)
        return " & ".join(texts)

    def strip_str_call(self, node: ast.expr) -> ast.expr:
        """`str(x)` inside a concatenation is redundant: & converts for us."""
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str"
                and len(node.args) == 1 and not node.keywords
                and self.b.resolve_callee(self.m, node.func) is None):
            return node.args[0]
        return node

    def str_lit(self, s: str) -> tuple[str, int]:
        return string_literal(s)

    # ------------------------------------------------------------- variables
    def var_info(self, py: str) -> Optional[VarInfo]:
        return self.vars.get(py)

    def is_local(self, py: str) -> bool:
        """Assigned somewhere in this function, so (as in Python) never a module-level name here."""
        if self.locals is None:
            self.locals = assigned_names(self.f.body)
        return py in self.locals

    def module_constant(self, node: ast.expr):
        """resolve_constant(), except for names the function assigns itself."""
        if isinstance(node, ast.Name) and self.is_local(node.id):
            return None
        return self.b.resolve_constant(self.m, node)

    def var_assign(self, py: str, t: FgType, node: ast.AST, declared: FgType = None) -> VarInfo:
        info = self.var_info(py)
        if info is None:
            want = legalize(py)
            fg = self.ns.reserve(want)
            if fg.lower() != want.lower():
                self.warn(f"variable '{py}' renamed to '{fg}' (Flowgorithm identifiers ignore case, have no "
                          f"underscores and are ASCII, so the name clashes with another one)", node)
            hint = self.hints.get(py) if declared is None else None
            info = VarInfo(py, fg, hint if isinstance(hint, str) else None, order=self.next_order(),
                           declared=declared, node=node)
            self.vars[py] = info
        elif declared is not None and info.declared is None and not info.is_param:
            if info.type is not None and not assignable(declared, info.type):
                raise self.err(f"'{py}' is annotated {py_type(declared)} but already holds {py_type(info.type)}",
                               node, self.annotation_hint(declared, info.type))
            info.declared = declared
        if info.is_const:
            raise self.err(f"cannot assign to constant '{py}'", node)
        if info.is_array:
            raise self.err(f"cannot reassign array '{py}'", node)
        self.stale.pop(py, None)
        if info.declared is not None:
            if declared is not None and declared != info.declared:
                raise self.err(f"'{py}' is annotated twice, as {py_type(info.declared)} and {py_type(declared)}", node)
            if t is not None and not assignable(info.declared, t):
                if info is self.ret_var and info.py != "<return>":
                    what = f"'{py}' is returned by {self.f.py_name}(), annotated `-> {py_type(info.declared)}`,"
                elif info.is_param:
                    what = f"parameter '{py}' is annotated {py_type(info.declared)}"
                else:
                    what = f"'{py}' is annotated {py_type(info.declared)}"
                raise self.err(f"{what} but is assigned {py_type(t)}", node,
                               self.annotation_hint(info.declared, t) or
                               "Flowgorithm variables have a single type; use another variable")
            info.type = info.declared
            return info
        old = info.type
        try:
            info.type = join_types(info.type, t)
        except TypeError as e:
            raise self.err(f"variable '{py}' is used with two types: {e}", node,
                           "Flowgorithm variables have a single type; use another variable")
        if old is not None and info.type != old:
            self.widened = True  # earlier uses saw the narrower type: the builder converts again
        return info

    def fresh_var(self, base: str, t: FgType) -> VarInfo:
        fg = self.ns.reserve(base)
        key = f"<{fg}>"
        info = VarInfo(key, fg, t, order=self.next_order())
        self.vars[key] = info
        return info

    def lookup(self, name: ast.Name) -> VarInfo:
        """Variable (or module constant) referenced by a Name in a load context."""
        info = self.vars.get(name.id)
        if info is not None:
            self.read_after.update(self.stale.get(name.id, ()))  # the next pass counts with a copy
            return info
        if self.is_local(name.id):
            raise self.err(f"'{name.id}' is not defined before use", name)
        const = self.b.resolve_constant(self.m, name)
        if const is not None:
            return self.use_constant(name.id, const)
        if self.b.is_module_variable(self.m, name):
            raise self.err(f"'{name.id}' is a module-level variable; Flowgorithm has no global variables", name,
                           "pass it to the function as a parameter (only module-level names that are "
                           "assigned once, to a literal, are copied into functions as constants)")
        if self.b.resolve_callee(self.m, name) is not None:
            raise self.err(f"function '{name.id}' used as a value", name)
        if self.b.module_alias_target(self.m, name.id) is not None:
            raise self.err(f"module '{name.id}' used as a value", name)
        raise self.err(f"'{name.id}' is not defined before use", name)

    def use_constant(self, key: str, const) -> VarInfo:
        node, t, text = const
        info = self.vars.get(key)
        if info is None:
            fg = self.ns.reserve(legalize(key.split(".")[-1]))
            info = VarInfo(key, fg, t, is_const=True, const_text=text, order=self.next_order())
            self.vars[key] = info
        return info

    # ----------------------------------------------------------- expressions
    def text(self, node: ast.expr) -> str:
        return self.expr(node)[0]

    def sub(self, node: ast.expr, prec: int, side: str = "left") -> str:
        return paren(self.expr(node), prec, side)

    def expr(self, node: ast.expr) -> tuple[str, int]:
        handler = getattr(self, "e_" + type(node).__name__, None)
        if handler is None:
            raise self.err(f"unsupported expression: {type(node).__name__}", node)
        return handler(node)

    def e_Constant(self, n: ast.Constant) -> tuple[str, int]:
        v = n.value
        if isinstance(v, bool):
            return ("true" if v else "false"), P_ATOM
        if isinstance(v, int):
            return str(v), P_ATOM
        if isinstance(v, float):
            return self.float_text(v, n)
        if isinstance(v, str):
            return self.str_lit(v)
        if v is None:
            raise self.err("None has no Flowgorithm equivalent", n)
        raise self.err(f"unsupported literal {v!r}", n)

    def float_text(self, v: float, n: ast.AST) -> tuple[str, int]:
        try:
            return float_literal(v)
        except ValueError as e:
            raise self.err(str(e), n) from None

    def e_Name(self, n: ast.Name) -> tuple[str, int]:
        if self.var_info(n.id) is None and not self.is_local(n.id):
            ext = self.b.resolve_import(self.m, n.id)  # from math import pi
            if ext is not None:
                return self.library_constant(ext[0], ext[1], n)
        return self.lookup(n).fg, P_ATOM

    def library_constant(self, module: str, name: str, n: ast.AST) -> tuple[str, int]:
        if module == "math":
            if name == "pi":
                return "pi", P_ATOM
            if name == "e":
                return "2.718281828459045", P_ATOM
            if name == "tau":
                return "2 * pi", P_MUL
        raise self.err(f"{module}.{name} is not supported", n)

    def e_UnaryOp(self, n: ast.UnaryOp) -> tuple[str, int]:
        if isinstance(n.op, ast.USub):
            inner = self.sub(n.operand, P_UNARY)
            if inner.startswith("-"):
                inner = f"({inner})"
            return f"-{inner}", P_UNARY
        if isinstance(n.op, ast.UAdd):
            return self.expr(n.operand)
        if isinstance(n.op, ast.Not):
            return self.truthy_expr(n)
        raise self.err("bitwise operators are not supported", n)

    def e_BinOp(self, n: ast.BinOp) -> tuple[str, int]:
        op = type(n.op)
        lt, rt = self.infer(n.left), self.infer(n.right)
        if BOOLEAN in (lt, rt) and not (op is ast.Add and STRING in (lt, rt)):
            # `total += a > b`: Python counts True as 1; Flowgorithm needs an If that picks 1 or 0
            left = self.bool_as_number(n.left) if lt == BOOLEAN else n.left
            if rt == BOOLEAN and lt != BOOLEAN and self.has_effects(n.left):
                raise self.err("a Boolean used as a number would have to run before a call that Python "
                               "makes first", n.right, "assign the earlier call's result to a variable first")
            right = self.bool_as_number(n.right) if rt == BOOLEAN else n.right
            return self.expr(ast.copy_location(ast.BinOp(left=left, op=n.op, right=right), n))
        if op in (ast.FloorDiv, ast.Mod) and not self.intdiv_warned and lt != STRING:
            if self.int_literal(n.left) is None or self.int_literal(n.right) is None:
                self.intdiv_warned = True
                self.warn("// and % follow Flowgorithm's truncation semantics: results differ from Python "
                          "when an operand is negative", n)
        if op is ast.Add:
            if lt == STRING or rt == STRING:
                left = self.sub(self.strip_str_call(n.left), P_CAT)
                right = self.sub(self.strip_str_call(n.right), P_CAT)
                return f"{left} & {right}", P_CAT
            if lt is None and rt is None:
                self.warn("cannot tell whether + adds numbers or joins strings here; assuming numbers", n)
            sym, p = "+", P_ADD
        elif op is ast.Sub:
            sym, p = "-", P_ADD
        elif op is ast.Mult:
            if lt == STRING or rt == STRING:
                raise self.err("string repetition is not supported", n)
            sym, p = "*", P_MUL
        elif op is ast.Div:
            sym, p = "/", P_MUL
        elif op is ast.Mod:
            if lt == STRING:
                raise self.err("% string formatting is not supported; use an f-string", n)
            if self.negative_literal(n.left) or self.negative_literal(n.right):
                self.warn("% with a negative operand: Flowgorithm keeps the sign of the dividend, Python "
                          "the sign of the divisor", n)
            sym, p = "%", P_MUL
        elif op is ast.Pow:
            sym, p = "^", P_POW
        elif op is ast.FloorDiv:
            if self.negative_literal(n.left) or self.negative_literal(n.right):
                self.warn("// with a negative operand: Int() truncates toward zero, Python rounds down", n)
            return f"Int({self.sub(n.left, P_MUL)} / {self.sub(n.right, P_MUL, 'right')})", P_ATOM
        else:
            raise self.err(f"operator {op.__name__} is not supported", n)
        return f"{self.sub(n.left, p)} {sym} {self.sub(n.right, p, 'right')}", p

    def negative_literal(self, node: ast.expr) -> bool:
        v = self.int_literal(node)
        return v is not None and v < 0

    def e_BoolOp(self, n: ast.BoolOp) -> tuple[str, int]:
        for v in n.values:  # as a value, `a or b` yields an operand in Python, not a Boolean
            t = self.infer(v)
            if t is not None and t != BOOLEAN:
                raise self.err(f"and/or between non-Boolean values ({type_name(t)}) has no Flowgorithm "
                               "equivalent", n, "compare explicitly, e.g. `x != 0 or y != 0`, or use an if")
        return self.truthy_expr(n)

    def e_Compare(self, n: ast.Compare) -> tuple[str, int]:
        for op in n.ops:
            if type(op) not in COMPARE_OP:
                raise self.err(f"comparison '{type(op).__name__}' is not supported", n,
                               "Flowgorithm has no `in`; compare against each value with == / or")
        operands = [n.left] + list(n.comparators)
        types = [self.infer(x) for x in operands]
        for (lt, rt) in zip(types, types[1:]):
            if lt is not None and rt is not None and not self.compatible(lt, rt):
                raise self.err(f"comparing {type_name(lt)} with {type_name(rt)}", n)
        texts = []  # in Python's order of evaluation
        for k, x in enumerate(operands):
            if 0 < k < len(operands) - 1 and has_call(x):  # `lo <= f() <= hi` uses f() twice: once
                x = self.hoist_value(x, "value", "the middle of a chained comparison")
            texts.append(self.expr(x))
        parts = [f"{paren(a, P_REL)} {COMPARE_OP[type(op)]} {paren(b, P_REL, 'right')}"
                 for op, a, b in zip(n.ops, texts, texts[1:])]
        if len(parts) == 1:
            return parts[0], P_REL
        return " and ".join(parts), P_AND

    def e_Attribute(self, n: ast.Attribute) -> tuple[str, int]:
        target = self.b.module_alias_target(self.m, n.value.id) if isinstance(n.value, ast.Name) else None
        if target == "math":
            return self.library_constant("math", n.attr, n)
        const = self.b.resolve_constant(self.m, n)
        if const is not None:
            key = ast.unparse(n)
            return self.use_constant(key, const).fg, P_ATOM
        if target is not None:
            raise self.err(f"'{ast.unparse(n)}' is not a function or constant of module {target}", n)
        raise self.err(f"attribute access '{ast.unparse(n)}' is not supported", n,
                       "Flowgorithm has no objects or methods")

    def e_Subscript(self, n: ast.Subscript) -> tuple[str, int]:
        if not isinstance(n.value, ast.Name):
            raise self.err("only variables can be indexed", n)
        info = self.lookup(n.value)
        if isinstance(info.type, ArrayT):
            return f"{info.fg}[{self.index_text(n, info)}]", P_ATOM
        if info.type == STRING:
            return f"Char({info.fg}, {self.index_text(n, info)})", P_ATOM
        raise self.err(f"'{n.value.id}' cannot be indexed (type {type_name(info.type)})", n)

    def e_JoinedStr(self, n: ast.JoinedStr) -> tuple[str, int]:
        items: list = []
        for part in n.values:
            s = const_str(part)
            if s is not None:
                items.append(("lit", s))
            elif isinstance(part, ast.FormattedValue):
                items.append(("expr", self.format_value(part)))
            else:  # pragma: no cover
                raise self.err("unsupported f-string part", part)
        if not items:
            return '""', P_ATOM
        if len(items) == 1 and items[0][0] == "expr":
            inner = items[0][1]
            if self.infer(inner) == STRING:
                return self.expr(inner)
            return f"ToString({self.text(inner)})", P_ATOM
        text = self.concat(items)
        return text, (P_CAT if " & " in text else P_ATOM)

    def format_value(self, fv: ast.FormattedValue) -> ast.expr:
        """Return an AST node equivalent to the formatted value (ToFixed for `:.2f`)."""
        if fv.conversion not in (-1, ord("s")):  # repr(): the same text for numbers (also f"{x=}")
            if not is_numeric(self.infer(fv.value)):
                raise self.err("!r / !a (and `=`) in f-strings are only supported for numbers", fv,
                               "Python's repr() quotes strings and capitalises True/False; write the text out")
        spec = ""
        if fv.format_spec is not None and fv.format_spec.values:
            if len(fv.format_spec.values) != 1 or const_str(fv.format_spec.values[0]) is None:
                raise self.err("nested format specs are not supported", fv)
            spec = const_str(fv.format_spec.values[0])
        if spec in ("", "d", "s"):
            return fv.value
        m = re.fullmatch(r"\.(\d+)[fF]", spec)
        if m:
            call = ast.Call(func=ast.Name(id="__tofixed__", ctx=ast.Load()),
                            args=[fv.value, ast.Constant(value=int(m.group(1)))], keywords=[])
            return ast.copy_location(ast.fix_missing_locations(call), fv)
        raise self.err(f"format spec '{spec}' is not supported (only .Nf)", fv)

    def e_IfExp(self, n: ast.IfExp) -> tuple[str, int]:
        raise self.err("conditional expressions are not supported", n, "use an if statement")

    def e_Call(self, n: ast.Call) -> tuple[str, int]:
        inp = self.match_input(n)
        if inp is not None:  # `total += int(input("n? "))`: read into a variable first
            mark = self.effects
            prompt, t = inp
            answer = self.fresh_var("answer", t)
            self.hoist(self.prompt_output(prompt) + [Input(answer.fg)], n, "input()", mark)
            return answer.fg, P_ATOM
        fn = n.func
        fi = self.b.resolve_callee(self.m, fn)
        if fi is not None:
            if fi.ret_type == VOID:
                raise self.err(f"{fi.py_name}() does not return a value", n)
            return self.user_call(n, fi), P_ATOM
        if n.keywords:
            raise self.err("keyword arguments are not supported", n)
        args = n.args
        if isinstance(fn, ast.Name):
            ext = self.b.resolve_import(self.m, fn.id)  # from math import sqrt
            if ext is not None:
                return self.library_call(ext[0], ext[1], args, n)
            return self.builtin_call(fn.id, args, n)
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            target = self.b.module_alias_target(self.m, fn.value.id)
            if target in ("math", "random"):
                return self.library_call(target, fn.attr, args, n)
            if self.var_info(fn.value.id) is not None or self.module_constant(fn.value) is not None:
                raise self.err(f"method '.{fn.attr}()' is not supported", n,
                               "Flowgorithm has no methods; use len(), s[i], & concatenation, comparisons")
        raise self.err(f"unsupported call '{ast.unparse(fn)}(...)'", n)

    def user_call(self, call: ast.Call, fi: "FuncInfo") -> str:
        if fi.is_main:
            raise self.err("main() cannot be called; Flowgorithm's Main only runs once", call)
        if call.keywords:
            raise self.err("keyword arguments are not supported in calls", call)
        for a in call.args:
            if isinstance(a, ast.Starred):
                raise self.err("*args in calls is not supported", a, "pass each argument separately")
        args = list(call.args)
        if len(args) < len(fi.params):
            for p in fi.params[len(args):]:
                if p.default is None:
                    raise self.err(f"{fi.py_name}() expects {len(fi.params)} arguments, got {len(args)}", call)
                args.append(p.default)
        if len(args) > len(fi.params):
            raise self.err(f"{fi.py_name}() expects {len(fi.params)} arguments, got {len(args)}", call)
        if fi.ret_type is None:
            raise self.err(f"the return type of {fi.py_name}() is not known yet (recursive calls)", call,
                           f"add a return annotation to {fi.py_name}()")
        texts = []
        for a, p in zip(args, fi.params):
            at = self.infer(a)
            if isinstance(p.type, ArrayT):
                if not isinstance(at, ArrayT):
                    raise self.err(f"parameter '{p.py_name}' of {fi.py_name}() expects a {py_type(p.type)}", a,
                                   "pass a list variable (Flowgorithm passes arrays by name)")
                if at.elem != p.type.elem:
                    raise self.err(f"parameter '{p.py_name}' of {fi.py_name}() expects a {py_type(p.type)}, "
                                   f"got a {py_type(at)}", a, "Flowgorithm array parameters must match exactly")
            elif at is not None and p.type is not None and not assignable(p.type, at):
                hint = self.annotation_hint(p.type, at)
                if p.type == INTEGER and at == REAL:
                    hint = (f"Flowgorithm would cut off the fraction: annotate '{p.py_name}' as float, "
                            f"or pass int(...)")
                raise self.err(f"parameter '{p.py_name}' of {fi.py_name}() is {py_type(p.type)} but gets "
                               f"{py_type(at)}", a, hint)
            texts.append(self.text(a))
        self.effects += 1
        return f"{fi.fg_name}({', '.join(texts)})"

    def library_call(self, module: str, name: str, args: list, n: ast.Call) -> tuple[str, int]:
        if module == "math":
            if name in MATH_FUNCS and len(args) == 1:
                if name == "floor":
                    self.warn("math.floor mapped to Int(), which truncates toward zero", n)
                return MATH_FUNCS[name][0].format(self.text(args[0])), P_ATOM
            if name == "pow" and len(args) == 2:
                return f"{self.sub(args[0], P_POW)} ^ {self.sub(args[1], P_POW)}", P_POW
            if name == "exp" and len(args) == 1:
                return f"2.718281828459045 ^ {self.sub(args[0], P_POW)}", P_POW
            if name == "ceil":
                raise self.err("math.ceil has no Flowgorithm equivalent", n, "use Int(x) + 1 after a check")
            raise self.err(f"math.{name} is not supported", n)
        if module == "random":
            self.effects += 1  # Random() draws the next number
            if name in ("randint", "randrange") and len(args) == 2:
                a, b = args
                if self.literal_int(a) == 0:
                    return f"Random({self.plus_one(b) if name == 'randint' else self.text(b)})", P_ATOM
                if has_call(a):  # `a + Random(b - a + 1)` uses the lower bound twice
                    self.effects -= 1
                    a = self.hoist_value(a, "low", f"the lower bound of {name}()")
                    self.effects += 1
                low = self.sub(a, P_ADD)
                return f"{low} + Random({self.minus_expr(b, a, 1 if name == 'randint' else 0)})", P_ADD
            if name == "randrange" and len(args) == 1:
                return f"Random({self.text(args[0])})", P_ATOM
            if name == "random" and not args:
                return "Random(1000000) / 1000000.0", P_MUL
            raise self.err(f"random.{name} is not supported", n, "use random.randint(a, b) or random.randrange(n)")
        raise self.err(f"{module}.{name} is not supported", n)

    def builtin_call(self, name: str, args: list, n: ast.Call) -> tuple[str, int]:
        def one() -> ast.expr:
            if len(args) != 1:
                raise self.err(f"{name}() takes exactly one argument here", n)
            return args[0]

        if name == "__tofixed__":
            return f"ToFixed({self.text(args[0])}, {self.text(args[1])})", P_ATOM
        if name == "len":
            a = one()
            t = self.infer(a)
            if isinstance(t, ArrayT):
                return f"Size({self.text(a)})", P_ATOM
            if t == STRING or t is None:
                if t is None:
                    self.warn("len() of a value of unknown type assumed to be a string", n)
                return f"Len({self.text(a)})", P_ATOM
            raise self.err(f"len() of a {type_name(t)}", n)
        if name == "int":
            a = one()
            t = self.infer(a)
            if t == BOOLEAN:  # int(x > 0) is 1 or 0
                return self.expr(self.bool_as_number(a))
            if t == STRING:
                return f"ToInteger({self.text(a)})", P_ATOM
            if t == REAL:
                return f"Int({self.text(a)})", P_ATOM
            if t == INTEGER:
                return self.expr(a)
            if t is None:
                self.warn("int() of a value of unknown type assumed to be a string", n)
                return f"ToInteger({self.text(a)})", P_ATOM
            raise self.err(f"int() of a {type_name(t)} is not supported", n)
        if name == "float":
            a = one()
            t = self.infer(a)
            if t == STRING:
                return f"ToReal({self.text(a)})", P_ATOM
            if is_numeric(t):
                return self.expr(a)
            if t is None:
                self.warn("float() of a value of unknown type assumed to be a string", n)
                return f"ToReal({self.text(a)})", P_ATOM
            raise self.err(f"float() of a {type_name(t)} is not supported", n)
        if name == "str":
            a = one()
            t = self.infer(a)
            if t == STRING:
                return self.expr(a)
            return f"ToString({self.text(a)})", P_ATOM
        if name == "abs":
            return f"Abs({self.text(one())})", P_ATOM
        if name == "round":
            if len(args) == 2:
                return f"ToReal(ToFixed({self.text(args[0])}, {self.text(args[1])}))", P_ATOM
            self.warn("round(x) mapped to Int(x + 0.5), which is wrong for negative numbers", n)
            return f"Int({self.sub(one(), P_ADD)} + 0.5)", P_ATOM
        if name == "pow" and len(args) == 2:
            return f"{self.sub(args[0], P_POW)} ^ {self.sub(args[1], P_POW)}", P_POW
        if name == "ord":
            return f"ToCode({self.text(one())})", P_ATOM
        if name == "chr":
            return f"ToChar({self.text(one())})", P_ATOM
        if name == "input":
            raise self.err("input() must be assigned directly to a variable", n,
                           "write `x = input(prompt)` or `n = int(input(prompt))`")
        if name == "print":
            raise self.err("print() cannot be used inside an expression", n)
        if name in ("min", "max"):
            raise self.err(f"{name}() has no Flowgorithm equivalent", n, "use an if statement")
        if name in ("range", "enumerate"):
            raise self.err(f"{name}() is only supported in a for loop header", n)
        if name == "bool":
            raise self.err("bool() is not supported", n, "compare explicitly, e.g. `x != 0`")
        raise self.err(f"unknown function '{name}'", n)

    # ---------------------------------------------------------------- types
    def annotation_type(self, ann: ast.expr) -> FgType:
        if isinstance(ann, ast.Name) and ann.id in {"int", "float", "str", "bool"}:
            return {"int": INTEGER, "float": REAL, "str": STRING, "bool": BOOLEAN}[ann.id]
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            try:
                inner = ast.parse(ann.value.strip(), mode="eval").body
            except SyntaxError:
                raise self.err(f"invalid type annotation {ann.value!r}", ann) from None
            return self.annotation_type(ast.copy_location(inner, ann))
        if (isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name)
                and ann.value.id in ("list", "List")):
            inner = self.annotation_type(ann.slice)
            if isinstance(inner, ArrayT):
                raise self.err("nested lists are not supported (Flowgorithm arrays are 1-D)", ann)
            return ArrayT(inner)
        raise self.err(f"unsupported type annotation '{ast.unparse(ann)}'", ann,
                       "use int, float, str, bool or list[...] of those")

    def infer(self, n: ast.expr) -> FgType:
        """Best-effort static type of an expression (None when unknown)."""
        if isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, bool):
                return BOOLEAN
            if isinstance(v, int):
                return INTEGER
            if isinstance(v, float):
                return REAL
            if isinstance(v, str):
                return STRING
            return None
        if isinstance(n, ast.Name):
            info = self.var_info(n.id)
            if info is not None:
                return info.type
            if self.is_local(n.id):
                return None
            const = self.b.resolve_constant(self.m, n)
            if const is not None:
                return const[1]
            ext = self.b.resolve_import(self.m, n.id)
            return REAL if ext is not None and ext[0] == "math" else None
        if isinstance(n, ast.JoinedStr):
            return STRING
        if isinstance(n, ast.UnaryOp):
            return BOOLEAN if isinstance(n.op, ast.Not) else self.infer(n.operand)
        if isinstance(n, (ast.BoolOp, ast.Compare)):
            return BOOLEAN
        if isinstance(n, ast.BinOp):
            lt, rt = self.infer(n.left), self.infer(n.right)
            op = type(n.op)
            if op is ast.Add and (lt == STRING or rt == STRING):
                return STRING
            lt, rt = (INTEGER if t == BOOLEAN else t for t in (lt, rt))  # True + 1 == 2
            if op is ast.Div:
                return REAL
            if op is ast.FloorDiv:
                return INTEGER
            if op is ast.Pow and self.negative_literal(n.right):
                return REAL
            if REAL in (lt, rt):
                return REAL
            if lt == INTEGER and rt == INTEGER:
                return INTEGER
            return None
        if isinstance(n, ast.Subscript):
            if isinstance(n.value, ast.Name):
                t = self.infer(n.value)
                if isinstance(t, ArrayT):
                    return t.elem
                if t == STRING:
                    return STRING
            return None
        if isinstance(n, ast.Attribute):
            if isinstance(n.value, ast.Name) and self.b.module_alias_target(self.m, n.value.id) == "math":
                return REAL
            const = self.b.resolve_constant(self.m, n)
            return const[1] if const is not None else None
        if isinstance(n, ast.Call):
            return self.infer_call(n)
        return None

    def infer_call(self, n: ast.Call) -> FgType:
        fi = self.b.resolve_callee(self.m, n.func)
        if fi is not None:
            return None if fi.ret_type == VOID else fi.ret_type
        fn = n.func
        if isinstance(fn, ast.Name):
            ext = self.b.resolve_import(self.m, fn.id)
            if ext is not None:
                return self.infer_library(ext[0], ext[1])
            name = fn.id
            if name in ("int", "len", "ord", "__tofixed__"):
                return INTEGER if name != "__tofixed__" else STRING
            if name == "float":
                return REAL
            if name in ("str", "chr", "input"):
                return STRING
            if name == "abs" and n.args:
                return self.infer(n.args[0])
            if name == "round":
                return REAL if len(n.args) == 2 else INTEGER
            if name == "pow":
                return REAL
            return None
        if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
            target = self.b.module_alias_target(self.m, fn.value.id)
            if target in ("math", "random"):
                return self.infer_library(target, fn.attr)
            if fn.attr == "strip":
                return STRING
        return None

    @staticmethod
    def infer_library(module: str, name: str) -> FgType:
        if module == "math":
            if name in MATH_FUNCS:
                return MATH_FUNCS[name][1]
            return REAL
        if module == "random":
            return REAL if name == "random" else INTEGER
        return None
