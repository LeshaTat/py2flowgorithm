"""Project level: discover modules, resolve imports/constants/functions, assemble a Program."""
from __future__ import annotations

import ast
import os
import tokenize
from dataclasses import dataclass, field
from typing import Optional

from .convert import FunctionConverter, assigned_names, literal_text
from .layout import KNOWN_DIRECTIVES, IgnorePass, header_end, parse_directive, scan_source
from .model import (ArrayT, BOOLEAN, ConvertError, FgType, Function, INTEGER, Namespace, Program, REAL,
                    STRING, VOID, Warning_, join_types, legalize)

MAX_PASSES = 6  # type-widening passes per function (types only grow, so this converges quickly)

IGNORED_DIRS = {"tests", "test", "__pycache__", ".git", "venv", ".venv", "env", "build", "dist",
                "node_modules", ".tox", ".mypy_cache", ".pytest_cache", "site-packages", ".idea", ".vscode"}
LIBRARY_MODULES = {"math", "random"}


def is_test_file(filename: str) -> bool:
    return (filename.startswith("test_") or filename.endswith("_test.py")
            or filename in ("conftest.py", "setup.py"))


@dataclass
class ParamInfo:
    py_name: str
    type: FgType  # for the current build: the annotation, or inferred from the call sites
    default: Optional[ast.expr] = None
    declared: FgType = None  # the annotation (None: inferred)


@dataclass
class FuncInfo:
    py_name: str
    module: "ModuleInfo"
    node: Optional[ast.FunctionDef]
    body: list  # without the docstring and without statements marked `# fg: ignore`
    docstring: Optional[str]
    params: list[ParamInfo]
    ret_type: FgType  # VOID, a type, or None while it still has to be inferred (per build)
    fg_name: str = ""
    ignored: bool = False
    is_main: bool = False
    converted: Optional[Function] = None
    declared_ret: FgType = None  # VOID, the annotation, or None when inferred

    @property
    def lineno(self) -> int:
        return self.node.lineno if self.node is not None else 1


@dataclass
class ModuleInfo:
    name: str
    path: str
    source: str
    lines: list[str]
    tree: ast.Module
    functions: dict[str, FuncInfo] = field(default_factory=dict)
    constants: dict[str, tuple[ast.expr, FgType, str]] = field(default_factory=dict)
    imports: dict[str, tuple[str, Optional[str]]] = field(default_factory=dict)
    comments: dict[int, str] = field(default_factory=dict)
    colons: list[tuple[int, int]] = field(default_factory=list)  # positions of ':' tokens
    skipped_lines: set[int] = field(default_factory=set)  # lines that went with `# fg: ignore`
    directives: dict[str, str] = field(default_factory=dict)
    docstring: Optional[str] = None
    guard: Optional[ast.If] = None  # the `if __name__ == "__main__":` block
    toplevel: list = field(default_factory=list)  # module-level statements other than defs/imports
    reassigned: set[str] = field(default_factory=set)  # module-level names bound more than once
    is_package: bool = False  # an __init__.py

    @property
    def main_guard(self) -> bool:
        return self.guard is not None

    @property
    def package(self) -> str:
        return self.name if self.is_package else self.name.rpartition(".")[0]


def is_main_guard(s: ast.stmt) -> bool:
    if not isinstance(s, ast.If) or not isinstance(s.test, ast.Compare):
        return False
    t = s.test
    return (isinstance(t.left, ast.Name) and t.left.id == "__name__" and len(t.ops) == 1
            and isinstance(t.ops[0], ast.Eq) and len(t.comparators) == 1
            and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value == "__main__")


def literal_value(node: ast.expr):
    """Python value of a literal constant node (int/float/str/bool, possibly negated); else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (bool, int, float, str)):
        return node.value
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool)):
        return -node.operand.value
    return None


def literal_type(value) -> FgType:
    if isinstance(value, bool):
        return BOOLEAN
    if isinstance(value, int):
        return INTEGER
    if isinstance(value, float):
        return REAL
    if isinstance(value, str):
        return STRING
    return None


def dotted(node: ast.expr) -> Optional[list[str]]:
    """['a', 'b', 'c'] for the expression a.b.c, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return parts[::-1]


class ProgramBuilder:
    def __init__(self, *, comments: bool = True, author: str = "", all_functions: bool = False):
        self.modules: dict[str, ModuleInfo] = {}
        self.failed: dict[str, ConvertError] = {}  # modules that could not be loaded, by name
        self.warnings: list[Warning_] = []
        self.comments_enabled = comments
        self.author = author
        self.all_functions = all_functions
        self.current: Optional[FuncInfo] = None

    # ----------------------------------------------------------------- input
    def warn(self, msg: str, filename: str = "", lineno: Optional[int] = None) -> None:
        self.warnings.append(Warning_(msg, filename, lineno))

    def add_source(self, source: str, name: str = "program", path: str = "<string>",
                   is_package: bool = False) -> ModuleInfo:
        m = self.load_module(name, path, source, is_package)
        self.modules[name] = m
        return m

    def add_file(self, path: str, name: str, is_package: bool = False) -> ModuleInfo:
        try:
            with tokenize.open(path) as fh:  # honours a PEP 263 coding line; UTF-8 (with BOM) otherwise
                source = fh.read()
        except (UnicodeDecodeError, LookupError, SyntaxError) as e:
            raise ConvertError(f"cannot read the file: {e}", None,
                               "save it as UTF-8 or declare its encoding with a `# -*- coding: ... -*-` line",
                               path) from None
        return self.add_source(source, name, path, is_package)

    def discover(self, root: str) -> list[str]:
        """Load every non-test module under root; returns the module names (in walk order)."""
        root = os.path.abspath(root)
        names: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.startswith("."))
            rel_dir = os.path.relpath(dirpath, root)
            parts = [] if rel_dir == "." else rel_dir.split(os.sep)
            for fn in sorted(filenames):
                if not fn.endswith(".py") or is_test_file(fn):
                    continue
                stem = fn[:-3]
                mod_parts = parts if stem == "__init__" else parts + [stem]
                if not mod_parts:
                    continue
                name = ".".join(mod_parts)
                path = os.path.join(dirpath, fn)
                try:
                    self.add_file(path, name, is_package=stem == "__init__")
                    names.append(name)
                except SyntaxError as e:
                    err = ConvertError(f"syntax error: {e.msg}", None, filename=path)
                    err.lineno = e.lineno
                    self.failed[name] = err
                    self.warn(f"skipped {fn}: syntax error: {e.msg}", path, e.lineno)
                except ConvertError as e:
                    # Only an error if the program actually uses this module (see module()).
                    self.failed[name] = e
                    self.warn(f"skipped {fn}: {e.msg} (only a problem if the program imports it)",
                              e.filename or path, e.lineno)
        return names

    def module(self, name: str) -> Optional[ModuleInfo]:
        """A loaded module by name; raises the stored error for a module that failed to load."""
        if name in self.failed:
            raise self.failed[name]
        return self.modules.get(name)

    def known(self, name: str) -> bool:
        return name in self.modules or name in self.failed

    def is_package(self, name: str) -> bool:
        """A loaded package, or a folder of modules without an __init__.py."""
        prefix = name + "."
        return self.known(name) or any(k.startswith(prefix) for k in list(self.modules) + list(self.failed))

    def load_module(self, name: str, path: str, source: str, is_package: bool = False) -> ModuleInfo:
        tree = ast.parse(source, path)
        m = ModuleInfo(name, path, source, source.splitlines(), tree, is_package=is_package)
        m.comments, m.colons = scan_source(source)
        for line, text in m.comments.items():
            d = parse_directive(text)
            if d is None:
                continue
            if d[0] not in KNOWN_DIRECTIVES:
                self.warn(f"unknown directive 'fg: {d[0]}' (known: {', '.join(sorted(KNOWN_DIRECTIVES))})",
                          path, line)
            elif d[0] in ("name", "title", "about", "author", "authors"):
                key = {"title": "name", "authors": "author"}.get(d[0], d[0])
                m.directives[key] = d[1]
        m.docstring = ast.get_docstring(tree)
        body = list(tree.body)
        if m.docstring is not None and body:
            body = body[1:]
        pre = IgnorePass(m, m.skipped_lines)
        kept = iter(pre.block(body, 1))
        ignored = {id(s) for s in pre.ignored}
        bindings: dict[str, int] = {}  # assignments per name since its last import
        for s in body:
            if id(s) in ignored:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.register_function(m, s, ignored=True)  # calling it is still reported
                continue
            s = next(kept)
            if isinstance(s, (ast.Import, ast.ImportFrom)):
                for a in s.names:  # the last binding of a name wins: an import replaces a constant
                    bound = a.asname or a.name.split(".")[0]
                    m.constants.pop(bound, None)
                    bindings.pop(bound, None)
                self.register_import(m, s)
            elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.register_function(m, s)
            elif isinstance(s, ast.ClassDef):
                raise ConvertError("classes are not supported; Flowgorithm only has functions", s,
                                   "mark it with `# fg: ignore` if it is only used by tests", path)
            elif is_main_guard(s):
                m.guard = s
                for n in s.body:
                    if isinstance(n, (ast.Import, ast.ImportFrom)):
                        self.register_import(m, n)
            else:
                m.toplevel.append(s)
                self.register_constant(m, s)
                for n in assigned_names([s]):
                    bindings[n] = bindings.get(n, 0) + 1
                    m.imports.pop(n, None)  # ...and an assignment replaces an import
        # A name assigned more than once (or to a computed value) is a variable, not a constant.
        for n, count in bindings.items():
            if count > 1:
                m.constants.pop(n, None)
            if n not in m.constants:
                m.reassigned.add(n)
        return m

    def register_import(self, m: ModuleInfo, node: ast.stmt) -> None:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    m.imports[a.asname] = (a.name, None)
                else:
                    root = a.name.split(".")[0]
                    m.imports.setdefault(root, (root, None))
                    m.imports[a.name] = (a.name, None)
            return
        assert isinstance(node, ast.ImportFrom)
        if node.module == "__future__":
            return
        if node.level:
            pkg = m.package.split(".") if m.package else []
            base = pkg[:len(pkg) - (node.level - 1)] if node.level > 1 else pkg
            mod = ".".join(base + ([node.module] if node.module else []))
        else:
            mod = node.module or ""
        for a in node.names:
            if a.name == "*":
                raise ConvertError("star imports are not supported", node, filename=m.path)
            m.imports[a.asname or a.name] = (mod, a.name)

    def register_function(self, m: ModuleInfo, node: ast.FunctionDef, ignored: bool = False) -> None:
        if ignored:  # never converted, so it may use any Python
            params = [ParamInfo(a.arg, None) for a in node.args.args]
            m.functions[node.name] = FuncInfo(node.name, m, node, [], None, params, VOID, ignored=True,
                                              declared_ret=VOID)
            return
        if isinstance(node, ast.AsyncFunctionDef):
            raise ConvertError("async functions are not supported", node, filename=m.path)
        if node.decorator_list:
            raise ConvertError("decorators are not supported", node,
                               "mark the function with `# fg: ignore` if it is only used by tests", m.path)
        a = node.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
            raise ConvertError("only plain positional parameters are supported", node, filename=m.path)
        params: list[ParamInfo] = []
        defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
        for arg, default in zip(a.args, defaults):
            t = self.annotation(m, arg.annotation) if arg.annotation is not None else None
            if default is not None and literal_value(default) is None:
                raise ConvertError("default values must be literals", default, filename=m.path)
            params.append(ParamInfo(arg.arg, t, default, declared=t))
        docstring = ast.get_docstring(node)
        stmts = list(node.body)
        if docstring is not None and stmts:
            stmts = stmts[1:]
        body = IgnorePass(m, m.skipped_lines).block(stmts, header_end(m, node) + 1)
        for s in body:  # `import math` inside a function: make the name known (module-wide)
            for n in ast.walk(s):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    self.register_import(m, n)
        if node.returns is not None:
            ret = self.annotation(m, node.returns, allow_none=True)
            if isinstance(ret, ArrayT):
                raise ConvertError("functions cannot return lists in Flowgorithm", node.returns, filename=m.path)
        else:
            has_value_return = any(isinstance(n, ast.Return) and n.value is not None
                                   and not (isinstance(n.value, ast.Constant) and n.value.value is None)
                                   for s in body for n in ast.walk(s))
            ret = None if has_value_return else VOID
        fi = FuncInfo(node.name, m, node, body, docstring, params, ret, declared_ret=ret)
        m.functions[node.name] = fi

    def annotation(self, m: ModuleInfo, ann: ast.expr, allow_none: bool = False) -> FgType:
        if allow_none and isinstance(ann, ast.Constant) and ann.value is None:
            return VOID
        if isinstance(ann, ast.Name) and ann.id in ("int", "float", "str", "bool"):
            return {"int": INTEGER, "float": REAL, "str": STRING, "bool": BOOLEAN}[ann.id]
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            try:
                inner = ast.parse(ann.value.strip(), mode="eval").body
            except SyntaxError:
                raise ConvertError(f"invalid type annotation {ann.value!r}", ann, filename=m.path) from None
            return self.annotation(m, ast.copy_location(inner, ann), allow_none)
        if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id in ("list", "List"):
            inner = self.annotation(m, ann.slice)
            if isinstance(inner, ArrayT):
                raise ConvertError("nested lists are not supported (Flowgorithm arrays are 1-D)", ann, filename=m.path)
            return ArrayT(inner)
        raise ConvertError(f"unsupported type annotation '{ast.unparse(ann)}'", ann,
                           "use int, float, str, bool or list[...] of those", m.path)

    def register_constant(self, m: ModuleInfo, s: ast.stmt) -> None:
        target = value = None
        if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
            target, value = s.targets[0].id, s.value
        elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) and s.value is not None:
            target, value = s.target.id, s.value
        if target is None:
            return
        v = literal_value(value)
        if v is None:
            return
        try:
            text = literal_text(v)
        except ValueError as e:
            raise ConvertError(str(e), value, "Flowgorithm has no exponent notation; compute the value "
                               "(e.g. 10 ^ -20) instead", m.path) from None
        m.constants[target] = (value, literal_type(v), text)

    # ------------------------------------------------------------ resolution
    def resolve_alias(self, m: ModuleInfo, name: str):
        v = m.imports.get(name)
        if v is None:
            return None
        mod, attr = v
        if attr is None:
            return ("module", self.locate_module(m, mod))
        if not mod:  # `from . import helpers` in a top-level module: a sibling module
            return ("module", attr) if self.known(attr) else ("attr", mod, attr)
        mod = self.locate_module(m, mod)
        if self.known(f"{mod}.{attr}"):
            return ("module", f"{mod}.{attr}")
        return ("attr", mod, attr)

    def locate_module(self, m: ModuleInfo, mod: str) -> str:
        """Map an imported module name onto a loaded module.

        `from prompts import ask_int` inside `examples/arith_quiz/quiz.py` refers to
        `examples/arith_quiz/prompts.py` even when the converter was pointed at a parent
        directory (where that module is known as `arith_quiz.prompts`). A sibling module wins
        over one of the same name higher up, as when the script is run from its own directory.
        """
        if mod in LIBRARY_MODULES:
            return mod
        pkg = m.package
        while pkg:
            cand = f"{pkg}.{mod}"
            if self.is_package(cand):
                return cand
            pkg = pkg.rpartition(".")[0]
        return mod

    def module_alias_target(self, m: ModuleInfo, name: str) -> Optional[str]:
        r = self.resolve_alias(m, name)
        return r[1] if r and r[0] == "module" else None

    def resolve_import(self, m: ModuleInfo, name: str) -> Optional[tuple[str, str]]:
        """('math', 'sqrt') for a name bound by `from math import sqrt` (non-project modules only)."""
        r = self.resolve_alias(m, name)
        if r and r[0] == "attr" and not self.known(r[1]):
            return r[1], r[2]
        return None

    def _member_of(self, m: ModuleInfo, name: str, depth: int = 0) -> Optional[tuple[ModuleInfo, str]]:
        """(module, name) where `name`, as seen from module m, is defined; follows re-exports such as
        `from .impl import f` in a package's __init__.py."""
        if name in m.functions or name in m.constants or name in m.reassigned:
            return m, name
        r = self.resolve_alias(m, name)
        if r and r[0] == "attr" and self.known(r[1]):
            target = self.module(r[1])
            found = self._member_of(target, r[2], depth + 1) if depth < 8 else None
            return found or (target, r[2])
        return None

    def _resolve_member(self, m: ModuleInfo, node: ast.expr) -> Optional[tuple[ModuleInfo, str]]:
        """(module, member name) that a Name / dotted Attribute refers to within the project."""
        if isinstance(node, ast.Name):
            return self._member_of(m, node.id)
        chain = dotted(node)
        if chain is None or len(chain) < 2:
            return None
        r = self.resolve_alias(m, chain[0])
        if r is None or r[0] != "module":
            return None
        modname, rest = r[1], chain[1:]
        while len(rest) > 1 and self.is_package(f"{modname}.{rest[0]}"):
            modname, rest = f"{modname}.{rest[0]}", rest[1:]
        if len(rest) != 1 or not self.known(modname):
            return None
        target = self.module(modname)
        return self._member_of(target, rest[0]) or (target, rest[0])

    def resolve_callee(self, m: ModuleInfo, func: ast.expr) -> Optional[FuncInfo]:
        r = self._resolve_member(m, func)
        if r is None:
            return None
        return r[0].functions.get(r[1])

    def resolve_constant(self, m: ModuleInfo, node: ast.expr):
        r = self._resolve_member(m, node)
        if r is None:
            return None
        mod, name = r
        if name in mod.functions:
            return None
        const = mod.constants.get(name)
        if const is None:
            return None
        # In a module-level program the "constants" of that module are ordinary statements of Main.
        cur = self.current
        if cur is not None and cur.is_main and cur.node is None and mod is cur.module:
            return None
        return const

    def is_module_variable(self, m: ModuleInfo, node: ast.expr) -> bool:
        """A module-level name that is assigned more than once or not to a literal."""
        r = self._resolve_member(m, node)
        return r is not None and r[1] in r[0].reassigned and r[1] not in r[0].functions

    # ---------------------------------------------------------------- build
    def callees(self, fi: FuncInfo) -> list[FuncInfo]:
        """Functions called from fi's body, skipping statements marked `# fg: ignore`."""
        seen: list[FuncInfo] = []

        def visit(stmts: list) -> None:
            for s in stmts:
                if not isinstance(s, ast.AST):
                    continue
                if isinstance(s, (ast.If, ast.While)):
                    roots = [s.test]
                elif isinstance(s, ast.For):
                    roots = [s.iter, s.target]
                else:
                    roots = [s]
                for root in roots:
                    for n in ast.walk(root):
                        if isinstance(n, ast.Call):
                            c = self.resolve_callee(fi.module, n.func)
                            if c is not None and c not in seen:
                                seen.append(c)
                for field in ("body", "orelse"):
                    visit(getattr(s, field, []) or [])

        visit(fi.body)
        return seen

    def infer_params(self, fi: FuncInfo, program: list[FuncInfo]) -> None:
        """Types of un-annotated parameters: the default's type joined with the literal arguments
        at the call sites in the functions of this program (other code does not count)."""
        for i, p in enumerate(fi.params):
            if p.declared is not None:
                continue
            seen: list[tuple[FgType, ast.AST]] = []
            if p.default is not None:
                seen.append((literal_type(literal_value(p.default)), p.default))
            for caller in program:
                for st in caller.body:
                    for n in ast.walk(st) if isinstance(st, ast.AST) else ():
                        if (isinstance(n, ast.Call) and i < len(n.args)
                                and self.resolve_callee(caller.module, n.func) is fi):
                            v = literal_value(n.args[i])
                            if v is not None:
                                seen.append((literal_type(v), n.args[i]))
            t: FgType = None
            for lt, node in seen:
                try:
                    t = join_types(t, lt)
                except TypeError:
                    raise ConvertError(f"parameter '{p.py_name}' of {fi.py_name}() is passed values of different "
                                       f"types ({t} and {lt}); it needs a type annotation", fi.node,
                                       f"write e.g. `def {fi.py_name}({p.py_name}: str)`", fi.module.path) from None
            p.type = t

    def entry_candidates(self) -> list[ModuleInfo]:
        mods = list(self.modules.values())
        guarded = [m for m in mods if m.main_guard]
        if guarded:
            return guarded
        with_main = [m for m in mods if "main" in m.functions]
        if with_main:
            return with_main
        scripts = [m for m in mods if any(not self.is_constant_stmt(m, s) for s in m.toplevel)]
        if scripts:
            return scripts
        if not mods and self.failed:
            raise next(iter(self.failed.values()))
        return []

    @staticmethod
    def entry_call_target(s: ast.stmt) -> Optional[ast.expr]:
        """`f` for a statement `f()`, `sys.exit(f())`, `exit(f())` or `raise SystemExit(f())`."""
        if isinstance(s, ast.Expr):
            call = s.value
        elif isinstance(s, ast.Raise) and s.exc is not None and s.cause is None:
            call = s.exc
        else:
            return None
        if (isinstance(call, ast.Call) and len(call.args) == 1 and not call.keywords
                and dotted(call.func) in (["sys", "exit"], ["exit"], ["quit"], ["SystemExit"])):
            call = call.args[0]
        if isinstance(call, ast.Call) and not call.args and not call.keywords:
            return call.func
        return None

    def guard_entry(self, m: ModuleInfo) -> Optional[FuncInfo]:
        """The function that the `if __name__ == "__main__":` block runs (usually main())."""
        target = None
        for s in m.guard.body:
            if isinstance(s, (ast.Import, ast.ImportFrom, ast.Pass)) or (
                    isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)):
                continue
            func = self.entry_call_target(s)
            fi = self.resolve_callee(m, func) if func is not None else None
            if fi is None or (target is not None and fi is not target):
                raise ConvertError("only a call of main() is supported inside `if __name__ == \"__main__\":`", s,
                                   "move this code into main()", m.path)
            target = fi
        if m.guard.orelse:
            raise ConvertError("an else branch on `if __name__ == \"__main__\":` is not supported",
                               m.guard.orelse[0], filename=m.path)
        return target

    def entry_function(self, entry: ModuleInfo) -> FuncInfo:
        """The function that becomes Main: the one the `__name__` guard calls, else main(), else a
        function made of the module-level code."""
        main_fi = self.guard_entry(entry) if entry.guard is not None else None
        if main_fi is None:
            main_fi = entry.functions.get("main")
        if main_fi is None:
            if not entry.toplevel:
                raise ConvertError("no main() function and no module-level code found", None,
                                   "write a `def main():` and call it under `if __name__ == \"__main__\":`",
                                   entry.path)
            return FuncInfo("main", entry, None, list(entry.toplevel), None, [], VOID, declared_ret=VOID)
        name = main_fi.py_name
        if main_fi.ignored:
            raise ConvertError(f"{name}() is the program's entry point but is marked `fg: ignore`", main_fi.node,
                               "remove the directive (or the call)", main_fi.module.path)
        if main_fi.params:
            raise ConvertError(f"{name}() must not take parameters (it becomes Flowgorithm's Main)", main_fi.node,
                               filename=main_fi.module.path)
        if main_fi.ret_type not in (VOID, None):
            raise ConvertError(f"{name}() must not return a value (it becomes Flowgorithm's Main)", main_fi.node,
                               filename=main_fi.module.path)
        for s in entry.toplevel:
            func = self.entry_call_target(s)
            if func is not None and self.resolve_callee(entry, func) is main_fi:
                continue  # a bare `main()` call at the end of the module
            if not self.is_constant_stmt(entry, s):
                raise ConvertError(f"module-level code is not supported when {name}() exists", s,
                                   f"move it into {name}(), make it a literal constant, or mark it "
                                   "`# fg: ignore`", entry.path)
        return main_fi

    def build(self, entry: ModuleInfo, title: str = "") -> Program:
        for m in self.modules.values():  # nothing from an earlier build (another entry) carries over
            for fi in m.functions.values():
                fi.is_main = False
                fi.converted = None
                fi.fg_name = ""
                fi.ret_type = fi.declared_ret
                for p in fi.params:
                    p.type = p.declared
        main_fi = self.entry_function(entry)
        main_fi.is_main = True
        main_fi.fg_name = "Main"
        main_fi.ret_type = VOID

        # Call graph: post-order so callees are converted (and typed) before their callers.
        order: list[FuncInfo] = []
        stack: list[FuncInfo] = []

        def visit(fi: FuncInfo, caller: Optional[FuncInfo]) -> None:
            if fi.ignored:
                raise ConvertError(f"{fi.py_name}() is marked `fg: ignore` but is called from "
                                   f"{caller.py_name if caller else 'the program'}()", fi.node,
                                   filename=fi.module.path)
            if fi in order or fi in stack:
                return
            stack.append(fi)
            for c in self.callees(fi):
                visit(c, fi)
            stack.pop()
            order.append(fi)

        visit(main_fi, None)
        if self.all_functions:
            for m in [entry] + [x for x in self.modules.values() if x is not entry]:
                for fi in m.functions.values():
                    if not fi.ignored and fi is not main_fi:
                        visit(fi, None)

        ns = Namespace({"main"})
        output_order = [main_fi] + sorted((fi for fi in order if fi is not main_fi),
                                          key=lambda f: (f.module is not entry,
                                                         list(self.modules).index(f.module.name), f.lineno))
        for fi in output_order:
            if fi is main_fi:
                continue
            want = legalize(fi.py_name)
            fi.fg_name = ns.reserve(want)
            if fi.fg_name.lower() != want.lower():
                self.warn(f"function '{fi.py_name}' renamed to '{fi.fg_name}' (name clash)", fi.module.path, fi.lineno)
        used: list[ModuleInfo] = []
        for fi in order:
            if not any(fi.module is u for u in used):
                used.append(fi.module)
        for m in used:
            if m is not main_fi.module and any(not self.is_constant_stmt(m, s) for s in m.toplevel):
                s = next(s for s in m.toplevel if not self.is_constant_stmt(m, s))
                self.warn(f"module-level code in {os.path.basename(m.path)} is not part of the flowchart "
                          f"(only functions and literal constants are taken from imported modules)",
                          m.path, s.lineno)
        for fi in order:
            self.infer_params(fi, order)
        for fi in order:
            self.current = fi
            fi.converted = self.convert_function(fi)
            if fi.ret_type is None:
                fi.ret_type = fi.converted.type
        self.current = None

        name = title or entry.directives.get("name") or self.default_title(entry)
        about = entry.directives.get("about") or (entry.docstring or "").strip()
        authors = entry.directives.get("author") or self.author
        return Program(name, [fi.converted for fi in output_order], authors, about)

    def convert_function(self, fi: FuncInfo) -> Function:
        """Convert one function; again with the final variable types when a variable widened from
        Integer to Real after it had been used (its earlier uses must see the Real)."""
        hints: dict[str, FgType] = {}
        for _ in range(MAX_PASSES):
            conv = FunctionConverter(self, fi.module, fi, hints)
            if fi.node is None:  # module-level program: comments of/inside defs belong to them
                for s in fi.module.tree.body:
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        conv.consumed.update(self.def_lines(fi.module, s))
                    elif isinstance(s, (ast.Import, ast.ImportFrom)) or is_main_guard(s):
                        conv.consumed.update(range(s.lineno, (s.end_lineno or s.lineno) + 1))
            fn = conv.convert()
            if not conv.widened:
                break
            hints = conv.type_hints()
        self.warnings.extend(conv.warnings)
        return fn

    def is_constant_stmt(self, m: ModuleInfo, s: ast.stmt) -> bool:
        """True for a literal assignment to a module constant (`X = 3`; also one that a later import
        of the same name replaces), not for `X = X + 1` or a name assigned twice."""
        if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
            name, value = s.targets[0].id, s.value
        elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) and s.value is not None:
            name, value = s.target.id, s.value
        else:
            return False
        return literal_value(value) is not None and name not in m.reassigned

    @staticmethod
    def def_lines(m: ModuleInfo, node: ast.FunctionDef) -> set[int]:
        """Source lines owned by a def: decorators, the comment block above it, its body and the
        indented comment lines that trail it."""
        first = min([node.lineno] + [d.lineno for d in node.decorator_list])
        last = node.end_lineno or node.lineno
        lines = set(range(first, last + 1))
        ln = first - 1
        while ln in m.comments:
            lines.add(ln)
            ln -= 1
        ln = last + 1
        while ln <= len(m.lines):
            raw = m.lines[ln - 1]
            if not raw.strip():
                ln += 1
                continue
            if ln in m.comments and len(raw) - len(raw.lstrip()) > node.col_offset:
                lines.add(ln)
                ln += 1
                continue
            break
        return lines

    @staticmethod
    def default_title(entry: ModuleInfo) -> str:
        if entry.docstring:
            first = entry.docstring.strip().splitlines()[0].strip().rstrip(".")
            if first:
                return first
        stem = entry.name.rpartition(".")[2] if entry.path.startswith("<") else \
            os.path.splitext(os.path.basename(entry.path))[0]
        return stem.replace("_", " ").strip().title() or "Program"
