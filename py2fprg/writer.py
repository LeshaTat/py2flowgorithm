"""Serialise the shape IR into Flowgorithm's .fprg XML, formatted the way Flowgorithm writes it."""
from __future__ import annotations

import base64
import datetime as _dt
import getpass
import socket

from .model import (Assign, Breakpoint, Call, Comment, Declare, Do, For, Function, If, Input,
                    Output, Program, While)


def esc(value: str) -> str:
    """Escape an attribute value: XML specials, control chars and non-ASCII as Flowgorithm does."""
    value = value.replace("\r\n", "\n")
    out = []
    for ch in value:
        if ch == "&":
            out.append("&amp;")
        elif ch == "<":
            out.append("&lt;")
        elif ch == ">":
            out.append("&gt;")
        elif ch == '"':
            out.append("&quot;")
        elif ch == "\n":
            out.append("&#13;&#10;")
        elif ord(ch) < 32 and ch not in "\t\r" or 0xD800 <= ord(ch) <= 0xDFFF or ord(ch) in (0xFFFE, 0xFFFF):
            continue  # XML 1.0 cannot carry these, not even as &#n;
        elif ord(ch) < 32 or ord(ch) > 126:
            out.append(f"&#{ord(ch)};")
        else:
            out.append(ch)
    return "".join(out)


def _tag(name: str, attrs: list[tuple[str, str]], self_close: bool) -> str:
    text = "<" + name + "".join(f' {k}="{esc(v)}"' for k, v in attrs)
    return text + ("/>" if self_close else ">")


class Writer:
    def __init__(self, indent: str = "    "):
        self.lines: list[str] = []
        self.indent = indent

    def line(self, depth: int, text: str) -> None:
        self.lines.append(self.indent * depth + text)

    def container(self, depth: int, name: str, attrs: list[tuple[str, str]], body: list) -> None:
        if not body:
            self.line(depth, _tag(name, attrs, True))
            return
        self.line(depth, _tag(name, attrs, False))
        self.statements(depth + 1, body)
        self.line(depth, f"</{name}>")

    def statements(self, depth: int, stmts: list) -> None:
        for s in stmts:
            self.statement(depth, s)

    def statement(self, depth: int, s) -> None:
        if isinstance(s, Declare):
            self.line(depth, _tag("declare", [("name", ", ".join(s.names)), ("type", s.type),
                                              ("array", "True" if s.array else "False"),
                                              ("size", s.size if s.array else "")], True))
        elif isinstance(s, Assign):
            self.line(depth, _tag("assign", [("variable", s.variable), ("expression", s.expression)], True))
        elif isinstance(s, Input):
            self.line(depth, _tag("input", [("variable", s.variable)], True))
        elif isinstance(s, Output):
            self.line(depth, _tag("output", [("expression", s.expression),
                                             ("newline", "True" if s.newline else "False")], True))
        elif isinstance(s, If):
            self.line(depth, _tag("if", [("expression", s.expression)], False))
            self.container(depth + 1, "then", [], s.then)
            self.container(depth + 1, "else", [], s.else_)
            self.line(depth, "</if>")
        elif isinstance(s, While):
            self.container(depth, "while", [("expression", s.expression)], s.body)
        elif isinstance(s, Do):
            self.container(depth, "do", [("expression", s.expression)], s.body)
        elif isinstance(s, For):
            self.container(depth, "for", [("variable", s.variable), ("start", s.start), ("end", s.end),
                                          ("direction", s.direction), ("step", s.step)], s.body)
        elif isinstance(s, Call):
            self.line(depth, _tag("call", [("expression", s.expression)], True))
        elif isinstance(s, Comment):
            self.line(depth, _tag("comment", [("text", s.text)], True))
        elif isinstance(s, Breakpoint):
            self.line(depth, "<breakpoint/>")
        else:  # pragma: no cover - programming error
            raise TypeError(f"unknown shape {s!r}")

    def function(self, f: Function) -> None:
        self.line(1, _tag("function", [("name", f.name), ("type", f.type), ("variable", f.variable)], False))
        if f.params:
            self.line(2, "<parameters>")
            for p in f.params:
                self.line(3, _tag("parameter", [("name", p.name), ("type", p.type),
                                                ("array", "True" if p.array else "False")], True))
            self.line(2, "</parameters>")
        else:
            self.line(2, "<parameters/>")
        self.container(2, "body", [], f.body)
        self.line(1, "</function>")


def _meta(author: str, now: _dt.datetime) -> tuple[str, str, str]:
    """Flowgorithm's ``saved``/``created``/``edited`` bookkeeping attributes."""
    saved = now.strftime("%Y-%m-%d %I:%M:%S %p")
    try:
        machine = socket.gethostname().split(".")[0] or "py2fprg"
    except OSError:  # pragma: no cover
        machine = "py2fprg"
    stamp = now.strftime("%Y-%m-%d;%I:%M:%S %p")
    created = base64.b64encode(f"{author};{machine};{stamp};0".encode()).decode()
    edited = base64.b64encode(f"{author};{machine};{stamp};1;0".encode()).decode()
    return saved, created, edited


def write_program(program: Program, fileversion: str = "3.0", now: _dt.datetime | None = None,
                  metadata: bool = True) -> str:
    """Return the complete .fprg document as a string."""
    now = now or _dt.datetime.now()
    author = program.authors or _default_author()
    w = Writer()
    w.line(0, '<?xml version="1.0"?>')
    w.line(0, f'<flowgorithm fileversion="{esc(fileversion)}">')
    w.line(1, "<attributes>")
    w.line(2, _tag("attribute", [("name", "name"), ("value", program.name)], True))
    w.line(2, _tag("attribute", [("name", "authors"), ("value", author)], True))
    w.line(2, _tag("attribute", [("name", "about"), ("value", program.about)], True))
    if metadata:
        saved, created, edited = _meta(author, now)
        w.line(2, _tag("attribute", [("name", "saved"), ("value", saved)], True))
        w.line(2, _tag("attribute", [("name", "created"), ("value", created)], True))
        w.line(2, _tag("attribute", [("name", "edited"), ("value", edited)], True))
    w.line(1, "</attributes>")
    for f in program.functions:
        w.function(f)
    w.line(0, "</flowgorithm>")
    return "\n".join(w.lines) + "\n"


def _default_author() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pragma: no cover
        return "py2fprg"
