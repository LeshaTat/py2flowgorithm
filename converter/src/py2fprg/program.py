"""One program in the Flowgorithm dialect -> one Flowgorithm Program.

The structure is fixed:

    \"\"\"Title of the program.

    What it does (becomes the program's description).\"\"\"
    from flowgorithm import *
    from seats import SEATS, seat_map   # functions and constants from files in the same folder

    LIMIT = 10                      # constants: literal values, copied into the functions using them

    def helper(n: int) -> int:      # functions: typed parameters, `return value` as the last statement
        ...

    def main():                     # the program itself: Flowgorithm's Main
        ...

    if __name__ == "__main__":
        main()

A flowchart holds all of its functions, so the functions a program imports from the files next
to it (and those files from theirs) go into its flowchart, as far as the program uses them.
Tests may sit in any of these files: `import unittest` and classes deriving from TestCase are
left out of the flowchart.
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
    names: set[str] = field(default_factory=set)  # the functions and constants this file defines or imports


@dataclass
class FuncInfo:
    name: str
    node: ast.FunctionDef
    body: list  # without the docstring and without statements marked `# fg: ignore`
    docstring: Optional[str]
    params: list[ParamInfo]
    ret_type: FgType  # the annotation (VOID for -> None), or None: from the return statement
    module: ModuleInfo  # the file it is written in
    imported: bool = False  # written in a file the program imports
    fg_name: str = ""
    is_main: bool = False


def is_main_guard(s: ast.stmt) -> bool:
    t = s.test if isinstance(s, ast.If) else None
    return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__"
            and len(t.ops) == 1 and isinstance(t.ops[0], ast.Eq) and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value == "__main__")


def is_test_code(s: ast.stmt) -> bool:
    """`import unittest` and test classes: they may sit next to the code they test, out of the flowchart."""
    if isinstance(s, ast.Import):
        return all(a.name == "unittest" or a.name.startswith("unittest.") for a in s.names)
    if isinstance(s, ast.ImportFrom):
        return not s.level and (s.module == "unittest" or (s.module or "").startswith("unittest."))
    if isinstance(s, ast.ClassDef):
        return any(isinstance(b, ast.Name) and b.id.endswith("TestCase")
                   or isinstance(b, ast.Attribute) and b.attr.endswith("TestCase") for b in s.bases)
    return False


class ProgramBuilder:
    def __init__(self, source: str, path: str = "<program>", *, comments: bool = True, author: str = ""):
        self.comments = comments
        self.author = author
        self.warnings: list[Warning_] = []
        self.functions: dict[str, FuncInfo] = {}
        self.ignored: set[str] = set()  # functions marked `# fg: ignore`
        self.constants: dict[str, object] = {}
        self.constant_files: dict[str, str] = {}  # constant -> the file that sets it
        self.modules: dict[str, ModuleInfo] = {}  # the files read for the imports, by their real path
        self.importing: list[str] = []  # the files being read, to report imports that go round in a circle
        self.module = self.parse(source, path)
        if os.path.isfile(path):
            self.importing.append(os.path.realpath(path))
        self.load(self.module, program=True)
        self.finish()

    @staticmethod
    def parse(source: str, path: str) -> ModuleInfo:
        try:
            tree = ast.parse(source, path)
        except SyntaxError as e:
            err = ConvertError(f"syntax error: {e.msg}", None, filename=path)
            err.lineno, err.col = e.lineno, (e.offset - 1 if e.offset else None)
            raise err from None
        return ModuleInfo(path, source, source.splitlines(), tree)

    def err(self, msg: str, node: Optional[ast.AST], hint: str = "", m: Optional[ModuleInfo] = None) -> ConvertError:
        return ConvertError(msg, node, hint, (m or self.module).path)

    def constant(self, name: str):
        return self.constants.get(name)

    # ----------------------------------------------------------------- input
    def load(self, m: ModuleInfo, program: bool) -> None:
        """Read one file: the program (program=True) or a file it imports."""
        m.comments, m.colons = scan_source(m.source)
        for line, text in m.comments.items():
            d = parse_directive(text)
            if d is None:
                continue
            if d[0] not in KNOWN_DIRECTIVES:
                self.warnings.append(Warning_(f"unknown directive 'fg: {d[0]}' (known: "
                                              f"{', '.join(sorted(KNOWN_DIRECTIVES))})", m.path, line))
            elif program and d[0] in ("name", "title", "about", "author", "authors"):
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
            if is_test_code(s):
                m.skipped_lines.update(range(s.lineno, s.end_lineno + 1))
            elif isinstance(s, ast.ImportFrom) and s.module == "flowgorithm" and not s.level:
                continue
            elif isinstance(s, ast.ImportFrom) and not s.level and s.module and "." not in s.module:
                self.load_import(m, s)
            elif isinstance(s, (ast.Import, ast.ImportFrom)):
                raise self.err("a Flowgorithm program imports only the library and files in its folder", s,
                               "`from flowgorithm import *`, `from seats import seat_map`", m)
            elif isinstance(s, ast.FunctionDef):
                if program or s.name != "main":  # another file's main() is that file's own program
                    self.register_function(m, s, imported=not program)
            elif isinstance(s, (ast.Assign, ast.AnnAssign)):
                self.register_constant(m, s)
            elif is_main_guard(s):
                if guard or s.orelse or len(s.body) != 1 or not self.calls_main(s.body[0]):
                    raise self.err("the `if __name__ == \"__main__\":` block only calls main()", s, m=m)
                guard = True
            else:
                raise self.err("at the top of the program go constants, functions and "
                               "`if __name__ == \"__main__\": main()`", s, "put this code into main()", m)

    def load_import(self, m: ModuleInfo, s: ast.ImportFrom) -> None:
        """`from seats import seat_map`: read seats.py, next to this file."""
        path = os.path.join(os.path.dirname(os.path.abspath(m.path)), s.module + ".py")
        if not (os.path.isfile(m.path) and os.path.isfile(path)):
            raise self.err(f"there is no file {s.module}.py next to {os.path.basename(m.path)}", s,
                           "a Flowgorithm program imports only the library and files in its own folder", m)
        key = os.path.realpath(path)
        if key in self.importing:
            files = [os.path.basename(p) for p in self.importing[self.importing.index(key):]] + [s.module + ".py"]
            raise self.err("these files import each other in a circle: " + " -> ".join(files), s,
                           "move what they share into a file of its own", m)
        module = self.modules.get(key)
        if module is None:
            try:
                with open(path, encoding="utf-8-sig") as fh:
                    source = fh.read()
            except (OSError, UnicodeDecodeError) as e:
                raise self.err(f"cannot read {s.module}.py: {e}", s, "save it as UTF-8", m) from None
            module = self.modules[key] = self.parse(source, path)
            self.importing.append(key)
            try:
                self.load(module, program=False)
            finally:
                self.importing.pop()
        for alias in s.names:
            if alias.name == "*":
                m.names |= module.names
            elif alias.name not in module.names:
                raise self.err(f"{s.module}.py has no function or constant '{alias.name}'", s, "", m)
            elif alias.asname not in (None, alias.name):
                raise self.err("import names as they are: `from seats import seat_map`", s, "", m)
            else:
                m.names.add(alias.name)

    def finish(self) -> None:
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
                    self.warnings.append(Warning_(note, fi.module.path, fi.node.lineno))

    @staticmethod
    def calls_main(s: ast.stmt) -> bool:
        return (isinstance(s, ast.Expr) and isinstance(s.value, ast.Call) and isinstance(s.value.func, ast.Name)
                and s.value.func.id == "main" and not s.value.args and not s.value.keywords)

    def register_function(self, m: ModuleInfo, node: ast.FunctionDef, imported: bool) -> None:
        if node.decorator_list:
            raise self.err("decorators are not part of the Flowgorithm dialect", node, m=m)
        a = node.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
            raise self.err("a function takes plain parameters: def f(a: int, b: str)", node, m=m)
        if a.defaults:
            raise self.err("Flowgorithm parameters have no default values", a.defaults[0],
                           "pass every argument in the calls", m)
        if node.name in self.functions:
            other = self.functions[node.name].module
            also = "" if other is m else f" (also in {os.path.basename(other.path)})"
            raise self.err(f"{node.name}() is defined twice{also}", node, m=m)
        params = []
        for arg in a.args:
            if arg.annotation is None:
                raise self.err(f"parameter '{arg.arg}' of {node.name}() needs a type", arg,
                               "write e.g. `def f(n: int, name: str, xs: list[float])`", m)
            try:
                params.append(ParamInfo(arg.arg, annotation_type(arg.annotation)))
            except ValueError as e:
                raise self.err(str(e), arg.annotation, m=m) from None
        ret: FgType = None
        if node.returns is not None:
            try:
                ret = annotation_type(node.returns, allow_none=True)
            except ValueError as e:
                raise self.err(str(e), node.returns, m=m) from None
            if not isinstance(ret, str):
                raise self.err("Flowgorithm functions return a single value, not an array", node.returns, m=m)
        docstring = ast.get_docstring(node)
        stmts = list(node.body)[1 if docstring is not None else 0:]
        body = IgnorePass(m, m.skipped_lines).block(stmts, header_end(m, node) + 1)
        self.functions[node.name] = FuncInfo(node.name, node, body, docstring, params, ret, m, imported)
        m.names.add(node.name)

    def register_constant(self, m: ModuleInfo, s: ast.stmt) -> None:
        target = s.targets[0] if isinstance(s, ast.Assign) and len(s.targets) == 1 else getattr(s, "target", None)
        if not isinstance(target, ast.Name) or s.value is None:
            raise self.err("at the top of the program go constants like `LIMIT = 10`", s, m=m)
        try:
            value = literal_value(s.value)
            literal_text(value)
        except ValueError as e:
            raise self.err("a constant is a literal value (a number, a string, True or False)" if str(e) == "not a literal"
                           else str(e), s.value, "compute other values in main()", m) from None
        if isinstance(s, ast.AnnAssign):
            try:
                t = annotation_type(s.annotation)
            except ValueError as e:
                raise self.err(str(e), s.annotation, m=m) from None
            if t != value_type(value) and not (t == "Real" and value_type(value) == "Integer"):
                raise self.err(f"'{target.id}' is annotated {type_name(t)} but its value is "
                               f"{type_name(value_type(value))}", s, m=m)
            if t == "Real":
                value = float(value)
        if target.id in self.constants:
            if self.constant_files[target.id] == m.path:
                raise self.err(f"the constant '{target.id}' is set twice", s, m=m)
            if self.constants[target.id] != value or type(self.constants[target.id]) is not type(value):
                raise self.err(f"the constant '{target.id}' is set differently in "
                               f"{os.path.basename(self.constant_files[target.id])}", s,
                               "set it in one file and import it from there", m)
        self.constants[target.id] = value
        self.constant_files.setdefault(target.id, m.path)
        m.names.add(target.id)

    # ----------------------------------------------------------------- build
    def build(self, title: str = "") -> Program:
        """Convert the program's functions and the imported ones they use, callees first (their return
        types are needed by the callers)."""
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
                        raise self.err(f"{n.func.id}() is marked `fg: ignore`, so it cannot be called", n,
                                       m=fi.module)
            conv = FunctionConverter(self, fi)
            fn = conv.convert()
            self.warnings += conv.warnings
            if fi.ret_type is None:
                fi.ret_type = fn.type
            converted[fi.name] = fn
            visiting.discard(fi.name)

        for fi in [f for f in self.functions.values() if not f.imported]:
            visit(fi)
        m = self.module
        name = title or m.directives.get("name") or self.default_title()
        about = m.directives.get("about") or (m.docstring or "").strip()
        own = [n for n, fi in self.functions.items() if not fi.imported and n != "main"]
        imported = [n for n, fi in self.functions.items() if fi.imported and n in converted]
        order = [converted["main"]] + [converted[n] for n in own + imported]
        return Program(name, order, m.directives.get("author") or self.author, about)

    def default_title(self) -> str:
        m = self.module
        if m.docstring and m.docstring.strip():
            return m.docstring.strip().splitlines()[0].strip().rstrip(".")
        stem = os.path.splitext(os.path.basename(m.path))[0].strip("<>")
        return stem.replace("_", " ").strip().title() or "Program"
