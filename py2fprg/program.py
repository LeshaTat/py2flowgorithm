"""One program file in the Flowgorithm dialect -> one Flowgorithm Program.

The structure is fixed:

    \"\"\"Title of the program.

    What it does (becomes the program's description).\"\"\"
    from flowgorithm import *

    LIMIT = 10                      # constants: literal values, copied into the functions using them

    def helper(n: int) -> int:      # functions: typed parameters, `return value` as the last statement
        ...

    def main():                     # the program itself: Flowgorithm's Main
        ...

    if __name__ == "__main__":
        main()
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from typing import Optional

from .convert import FunctionConverter, annotation_type, literal_text, literal_value, value_type
from .layout import KNOWN_DIRECTIVES, IgnorePass, header_end, parse_directive, scan_source
from .model import (ConvertError, FgType, Function, Namespace, Program, VOID, Warning_, legalize, rename_note,
                    type_name)


@dataclass
class ParamInfo:
    name: str
    type: FgType


@dataclass
class FuncInfo:
    name: str
    node: ast.FunctionDef
    body: list  # without the docstring and without statements marked `# fg: ignore`
    docstring: Optional[str]
    params: list[ParamInfo]
    ret_type: FgType  # the annotation (VOID for -> None), or None: from the return statement
    fg_name: str = ""
    is_main: bool = False


@dataclass
class ModuleInfo:
    path: str
    source: str
    lines: list[str]
    tree: ast.Module
    comments: dict[int, str] = field(default_factory=dict)
    colons: list[tuple[int, int]] = field(default_factory=list)
    skipped_lines: set[int] = field(default_factory=set)
    directives: dict[str, str] = field(default_factory=dict)
    docstring: Optional[str] = None


def is_main_guard(s: ast.stmt) -> bool:
    t = s.test if isinstance(s, ast.If) else None
    return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__"
            and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq) and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value == "__main__")


class ProgramBuilder:
    def __init__(self, source: str, path: str = "<program>", *, comments: bool = True, author: str = ""):
        self.comments = comments
        self.author = author
        self.warnings: list[Warning_] = []
        self.functions: dict[str, FuncInfo] = {}
        self.ignored: set[str] = set()  # functions marked `# fg: ignore`
        self.constants: dict[str, object] = {}
        try:
            tree = ast.parse(source, path)
        except SyntaxError as e:
            err = ConvertError(f"syntax error: {e.msg}", None, filename=path)
            err.lineno, err.col = e.lineno, (e.offset - 1 if e.offset else None)
            raise err from None
        self.module = ModuleInfo(path, source, source.splitlines(), tree)
        self.load()

    def err(self, msg: str, node: Optional[ast.AST], hint: str = "") -> ConvertError:
        return ConvertError(msg, node, hint, self.module.path)

    def constant(self, name: str):
        return self.constants.get(name)

    # ----------------------------------------------------------------- input
    def load(self) -> None:
        m = self.module
        m.comments, m.colons = scan_source(m.source)
        for line, text in m.comments.items():
            d = parse_directive(text)
            if d is None:
                continue
            if d[0] not in KNOWN_DIRECTIVES:
                self.warnings.append(Warning_(f"unknown directive 'fg: {d[0]}' (known: "
                                              f"{', '.join(sorted(KNOWN_DIRECTIVES))})", m.path, line))
            elif d[0] in ("name", "title", "about", "author", "authors"):
                m.directives[{"title": "name", "authors": "author"}.get(d[0], d[0])] = d[1]
        m.docstring = ast.get_docstring(m.tree)
        body = list(m.tree.body)[1 if m.docstring is not None else 0:]
        pre = IgnorePass(m, m.skipped_lines)
        kept = iter(pre.block(body, 1))
        ignored = {id(s) for s in pre.ignored}
        guard = False
        for s in body:
            if id(s) in ignored:
                if isinstance(s, ast.FunctionDef):
                    self.ignored.add(s.name)
                continue
            s = next(kept)
            if isinstance(s, ast.ImportFrom) and s.module == "flowgorithm" and not s.level:
                continue
            if isinstance(s, (ast.Import, ast.ImportFrom)):
                raise self.err("a Flowgorithm program imports only the library: `from flowgorithm import *`", s,
                               "Output, Input, Len, Char, ToInteger, Random, ... are all in it")
            if isinstance(s, ast.FunctionDef):
                self.register_function(s)
            elif isinstance(s, (ast.Assign, ast.AnnAssign)):
                self.register_constant(s)
            elif is_main_guard(s):
                if guard or s.orelse or len(s.body) != 1 or not self.calls_main(s.body[0]):
                    raise self.err("the `if __name__ == \"__main__\":` block only calls main()", s)
                guard = True
            else:
                raise self.err("at the top of the program go constants, functions and "
                               "`if __name__ == \"__main__\": main()`", s, "put this code into main()")
        main = self.functions.get("main")
        if main is None:
            raise self.err("the program needs a `def main():`", None,
                           "main() is Flowgorithm's Main; call it under `if __name__ == \"__main__\":`")
        if main.params:
            raise self.err("main() takes no parameters", main.node)
        if main.ret_type not in (None, VOID):
            raise self.err("main() returns no value", main.node)
        main.is_main, main.fg_name, main.ret_type = True, "Main", VOID
        ns = Namespace({"main"})
        for fi in self.functions.values():
            if not fi.is_main:
                want = legalize(fi.name)
                fi.fg_name = ns.reserve(want)
                note = rename_note("function", fi.name, fi.fg_name)
                if note:
                    self.warnings.append(Warning_(note, m.path, fi.node.lineno))

    @staticmethod
    def calls_main(s: ast.stmt) -> bool:
        return (isinstance(s, ast.Expr) and isinstance(s.value, ast.Call) and isinstance(s.value.func, ast.Name)
                and s.value.func.id == "main" and not s.value.args and not s.value.keywords)

    def register_function(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            raise self.err("decorators are not part of the Flowgorithm dialect", node)
        a = node.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
            raise self.err("a function takes plain parameters: def f(a: int, b: str)", node)
        if a.defaults:
            raise self.err("Flowgorithm parameters have no default values", a.defaults[0],
                           "pass every argument in the calls")
        if node.name in self.functions:
            raise self.err(f"{node.name}() is defined twice", node)
        params = []
        for arg in a.args:
            if arg.annotation is None:
                raise self.err(f"parameter '{arg.arg}' of {node.name}() needs a type", arg,
                               "write e.g. `def f(n: int, name: str, xs: list[float])`")
            try:
                params.append(ParamInfo(arg.arg, annotation_type(arg.annotation)))
            except ValueError as e:
                raise self.err(str(e), arg.annotation) from None
        ret: FgType = None
        if node.returns is not None:
            try:
                ret = annotation_type(node.returns, allow_none=True)
            except ValueError as e:
                raise self.err(str(e), node.returns) from None
            if not isinstance(ret, str):
                raise self.err("Flowgorithm functions return a single value, not an array", node.returns)
        docstring = ast.get_docstring(node)
        stmts = list(node.body)[1 if docstring is not None else 0:]
        body = IgnorePass(self.module, self.module.skipped_lines).block(stmts, header_end(self.module, node) + 1)
        self.functions[node.name] = FuncInfo(node.name, node, body, docstring, params, ret)

    def register_constant(self, s: ast.stmt) -> None:
        target = s.targets[0] if isinstance(s, ast.Assign) and len(s.targets) == 1 else getattr(s, "target", None)
        if not isinstance(target, ast.Name) or s.value is None:
            raise self.err("at the top of the program go constants like `LIMIT = 10`", s)
        try:
            value = literal_value(s.value)
            literal_text(value)
        except ValueError as e:
            raise self.err("a constant is a literal value (a number, a string, True or False)" if str(e) == "not a literal"
                           else str(e), s.value, "compute other values in main()") from None
        if isinstance(s, ast.AnnAssign):
            try:
                t = annotation_type(s.annotation)
            except ValueError as e:
                raise self.err(str(e), s.annotation) from None
            if t != value_type(value) and not (t == "Real" and value_type(value) == "Integer"):
                raise self.err(f"'{target.id}' is annotated {type_name(t)} but its value is "
                               f"{type_name(value_type(value))}", s)
            if t == "Real":
                value = float(value)
        if target.id in self.constants:
            raise self.err(f"the constant '{target.id}' is set twice", s)
        self.constants[target.id] = value

    # ----------------------------------------------------------------- build
    def build(self, title: str = "") -> Program:
        """Convert every function, callees first (their return types are needed by the callers)."""
        converted: dict[str, Function] = {}
        visiting: set[str] = set()

        def visit(fi: FuncInfo) -> None:
            if fi.name in converted or fi.name in visiting:
                return
            visiting.add(fi.name)
            for n in (n for st in fi.body for n in ast.walk(st)):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    callee = self.functions.get(n.func.id)
                    if callee is not None:
                        visit(callee)
                    elif n.func.id in self.ignored:
                        raise self.err(f"{n.func.id}() is marked `fg: ignore`, so it cannot be called", n)
            conv = FunctionConverter(self, fi)
            fn = conv.convert()
            self.warnings += conv.warnings
            if fi.ret_type is None:
                fi.ret_type = fn.type
            converted[fi.name] = fn
            visiting.discard(fi.name)

        for fi in self.functions.values():
            visit(fi)
        m = self.module
        name = title or m.directives.get("name") or self.default_title()
        about = m.directives.get("about") or (m.docstring or "").strip()
        order = [converted["main"]] + [converted[n] for n in self.functions if n != "main"]
        return Program(name, order, m.directives.get("author") or self.author, about)

    def default_title(self) -> str:
        m = self.module
        if m.docstring and m.docstring.strip():
            return m.docstring.strip().splitlines()[0].strip().rstrip(".")
        stem = os.path.splitext(os.path.basename(m.path))[0].strip("<>")
        return stem.replace("_", " ").strip().title() or "Program"
