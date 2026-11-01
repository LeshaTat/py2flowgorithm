#!/usr/bin/env python3
"""Render Flowgorithm ``.fprg`` files as flowcharts with Graphviz.

Usage::

    python3 fprg2svg.py INPUT.fprg [-o OUTPUT.(svg|png|pdf|dot)] [--function NAME] [--dot]

The script is standard-library only.  It parses the Flowgorithm XML (see
``docs/fprg-format.md``), generates DOT text itself and shells out to Graphviz
``dot`` for ``.svg`` / ``.png`` / ``.pdf`` (any other extension is passed to dot
as ``-T<ext>``).  ``-o file.dot`` or ``--dot`` writes the DOT source instead of
calling dot.  The default output path is the input path with the extension
replaced by ``.svg`` (``.dot`` with ``--dot``).

Programmatic use::

    from fprg2svg import fprg_to_dot
    dot_text = fprg_to_dot(xml_text)                  # every function, Main first
    dot_text = fprg_to_dot(xml_text, function="Area")  # one function only

Layout conventions (mirroring Flowgorithm as far as Graphviz allows):

* one cluster per function, flow top-to-bottom, Main first;
* If: diamond, False branch exits left, True branch exits right, both rejoin
  at an invisible merge point so the chart continues straight down;
* While / For: hexagon, True goes straight down into the body, the loop-back
  edge climbs the right-hand side back into the hexagon, False bypasses the
  body on the left;
* Do: body first, hexagon below it, True loops back up the right-hand side to
  the first body statement, False continues below;
* Comment: yellow note hanging off the flow on a dashed line (not part of the
  flow); Breakpoint: small red octagon; unknown elements: grey box with the
  tag name.

Every branch and loop body is wrapped in an invisible cluster so that nested
structures stay contiguous and never interleave with their surroundings.

Exit status: 0 on success, 1 for unreadable/malformed input or an unknown
function name, 2 when Graphviz ``dot`` is missing or fails.
"""

from __future__ import annotations

import argparse
import html
import os
import shutil
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from typing import NamedTuple, Sequence

__all__ = ["FprgError", "fprg_to_dot", "find_dot", "render_dot", "main"]

DEFAULT_WRAP = 60  # soft-wrap label lines longer than this many characters (0 = never)
DEFAULT_SPLINES = "spline"
FONT = "Helvetica"

# Edge weights.  Flow edges are heavier than edges into merge points so that a
# branch hugs the top of its diamond instead of floating down; the invisible
# "spine" edges are heavier still so the main flow stays vertical.
FLOW_WEIGHT = 2
JOIN_WEIGHT = 1
SPINE_WEIGHT = 4

# Places to look for dot when it is not on PATH (Homebrew, MacPorts/manual, distro).
DOT_CANDIDATES = ("/opt/homebrew/bin/dot", "/usr/local/bin/dot", "/opt/local/bin/dot", "/usr/bin/dot")

# Shape + colour per statement kind.  Colours approximate Flowgorithm's
# "Classic" scheme (orange declare, yellow assign, blue input, green output...).
STYLE: dict[str, dict[str, str]] = {
    "terminal": dict(shape="box", style="rounded,filled", fillcolor="#EDE7F6", color="#5E4B8B"),
    "declare": dict(shape="box", peripheries="2", style="filled", fillcolor="#FFE3C2", color="#B56A1F"),
    "assign": dict(shape="box", style="filled", fillcolor="#FFF4BF", color="#A98C0B"),
    "input": dict(shape="parallelogram", style="filled", fillcolor="#D6E8FF", color="#2F6DB5"),
    "output": dict(shape="parallelogram", style="filled", fillcolor="#D9F2D0", color="#3C8C3C"),
    "if": dict(shape="diamond", style="filled", fillcolor="#FFF9D6", color="#B59B00"),
    "loop": dict(shape="hexagon", style="filled", fillcolor="#E3F1F5", color="#2E7C8F"),
    "call": dict(shape="plain"),  # HTML table with vertical side bars ("predefined process")
    "comment": dict(shape="note", style="filled", fillcolor="#FFF59D", color="#B8A000", fontsize="9"),
    "breakpoint": dict(shape="octagon", style="filled", fillcolor="#E53935", color="#8E0000",
                       fontcolor="white", fontsize="9", margin="0.08,0.04"),
    "unknown": dict(shape="box", style="filled", fillcolor="#E0E0E0", color="#757575", fontcolor="#333333"),
}
CALL_FILL, CALL_BORDER = "#EADCF8", "#7B4FA6"


class FprgError(Exception):
    """Malformed input or an unknown function name."""


# --------------------------------------------------------------------------- text helpers

class Raw(str):
    """An attribute value that is already valid DOT (quoted string or HTML label)."""


def _q(s: str) -> Raw:
    """Quote text as a DOT double-quoted string (escString).

    Only backslash and double quote need escaping; a real newline is written as
    the ``\\n`` escape.  ``<``, ``>`` and ``&`` are literal inside quotes.
    """
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return Raw('"' + s + '"')


def _lines(text: str, wrap: int) -> list[str]:
    """Split label text on CR/LF and soft-wrap over-long lines at spaces.

    The characters of the text are never altered; wrapping only inserts line
    breaks at existing whitespace (words longer than ``wrap`` are left intact).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for raw in text.split("\n"):
        if wrap and len(raw) > wrap:
            out.extend(textwrap.wrap(raw, wrap, break_long_words=False, break_on_hyphens=False,
                                     replace_whitespace=False) or [raw])
        else:
            out.append(raw)
    return out


def _label(lines: list[str]) -> Raw:
    """DOT label for ``lines``: centred when single-line, left-justified otherwise."""
    if len(lines) <= 1:
        return _q(lines[0] if lines else "")
    esc = [ln.replace("\\", "\\\\").replace('"', '\\"') for ln in lines]
    return Raw('"' + "\\l".join(esc) + '\\l"')


def _html_text(lines: list[str]) -> str:
    esc = [html.escape(ln, quote=False).replace('"', "&quot;") for ln in lines]
    if len(esc) <= 1:
        return esc[0] if esc else ""
    return "".join(ln + '<BR ALIGN="LEFT"/>' for ln in esc)


def _call_label(lines: list[str]) -> Raw:
    """HTML label drawing a box with vertical bars on both sides."""
    return Raw(
        '<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5" '
        f'BGCOLOR="{CALL_FILL}" COLOR="{CALL_BORDER}">'
        '<TR><TD WIDTH="7"></TD><VR/><TD>' + _html_text(lines) + '</TD><VR/><TD WIDTH="7"></TD></TR>'
        '</TABLE>>'
    )


def _attrs(attrs: dict[str, object]) -> str:
    parts = []
    for key, value in attrs.items():
        parts.append(f"{key}={value if isinstance(value, Raw) else _q(str(value))}")
    return ", ".join(parts)


def _attr(el: ET.Element, *names: str, default: str = "") -> str:
    """First present attribute among ``names`` (``name`` vs 1.0-era ``variables``)."""
    for name in names:
        value = el.get(name)
        if value is not None:
            return value
    return default


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


# --------------------------------------------------------------------------- statement labels

def _declare_label(el: ET.Element) -> str:
    names = _attr(el, "name", "variables").strip()
    typ = el.get("type", "").strip()
    if _is_true(el.get("array")):
        names = f"{names}[{el.get('size', '').strip()}]"
    elif "," in names:
        names = ", ".join(part.strip() for part in names.split(",") if part.strip())
    return " ".join(part for part in ("Declare", typ, names) if part)


def _for_label(el: ET.Element) -> str:
    word = "downto" if el.get("direction", "inc").strip().lower() == "dec" else "to"
    return (f"for {el.get('variable', '')} = {el.get('start', '')} {word} {el.get('end', '')}"
            f" step {el.get('step', '1')}")


def _unknown_label(el: ET.Element) -> str:
    lines = [f"<{el.tag}>"]
    lines.extend(f'{key}="{value}"' for key, value in el.attrib.items())
    return "\n".join(lines)


def _function_labels(fel: ET.Element) -> tuple[str, str]:
    """(start terminal label, end terminal label) for a <function> element."""
    name = fel.get("name", "") or "Main"
    params = []
    pel = fel.find("parameters")
    for p in (pel if pel is not None else []):
        if p.tag != "parameter":
            continue
        text = f"{p.get('type', '')} {p.get('name', '')}".strip()
        if _is_true(p.get("array")):
            text += "[]"
        params.append(text)
    if name.lower() == "main" and not params:
        start = name
    else:
        start = f"{name}({', '.join(params)})"
    ftype = fel.get("type", "None").strip()
    variable = fel.get("variable", "").strip()
    end = f"Return {variable}" if ftype and ftype.lower() != "none" and variable else "End"
    return start, end


# --------------------------------------------------------------------------- DOT builder

class _Exit(NamedTuple):
    """Where the flow leaves a statement: node id, optional port and edge label."""
    node: str
    port: str | None = None
    label: str | None = None

    @property
    def ref(self) -> str:
        return f"{self.node}:{self.port}" if self.port else self.node


class _Stmt(NamedTuple):
    """Result of rendering one statement."""
    entry: str                   # node the flow enters
    exit: _Exit
    anchor: str                  # node (in the current cluster) that leading comments hang off


class _Block(NamedTuple):
    """Result of rendering a statement sequence."""
    entry: str | None            # first flow node, None when the block has no flow statements
    exit: _Exit | None
    comments: list[ET.Element]   # comments that found nothing in the block to attach to


class _DotBuilder:
    def __init__(self, wrap: int):
        self.wrap = wrap
        self.lines: list[str] = []
        self._count = 0
        self._clusters = 0
        self._indent = "    "
        self._last_comment: dict[str, str] = {}  # anchor node id -> last note attached to it

    # -- primitives -----------------------------------------------------------
    def emit(self, text: str) -> None:
        self.lines.append(self._indent + text)

    def _new_id(self) -> str:
        self._count += 1
        return f"n{self._count}"

    def node(self, kind: str, text: str, **extra: object) -> str:
        nid = self._new_id()
        attrs: dict[str, object] = dict(STYLE[kind])
        lines = _lines(text, self.wrap)
        attrs["label"] = _call_label(lines) if kind == "call" else _label(lines)
        attrs.update(extra)
        self.emit(f"{nid} [{_attrs(attrs)}];")
        return nid

    def point(self) -> str:
        nid = self._new_id()
        self.emit(f'{nid} [shape=point, width=0, height=0, label=""];')
        return nid

    def edge(self, tail: str, head: str, **attrs: object) -> None:
        text = f"{tail} -> {head}"
        if attrs:
            text += f" [{_attrs(attrs)}]"
        self.emit(text + ";")

    def connect(self, exit_: _Exit, head: str, **attrs: object) -> None:
        """Flow edge from a statement's exit to the next node."""
        if exit_.label:
            attrs.setdefault("taillabel", exit_.label)
        attrs.setdefault("weight", FLOW_WEIGHT)
        self.edge(exit_.ref, head, **attrs)

    def open_cluster(self, **attrs: object) -> None:
        self._clusters += 1
        self.emit(f"subgraph cluster_{self._clusters} {{")
        self._indent += "    "
        if attrs:
            self.emit(_attrs(attrs).replace(", ", "; ") + ";")

    def close_cluster(self) -> None:
        self._indent = self._indent[:-4]
        self.emit("}")

    # -- comments -------------------------------------------------------------
    def comment(self, el: ET.Element, anchor: str) -> None:
        """Yellow note to the right of ``anchor`` (same rank, dashed connector)."""
        target = self._last_comment.get(anchor, anchor)
        note = self.node("comment", el.get("text", ""))
        self.emit(f"{{ rank=same; {target}; {note}; }}")
        self.emit(f'{target} -> {note} [style=dashed, arrowhead=none, color="#9E9E9E"];')
        self._last_comment[anchor] = note

    # -- statements -----------------------------------------------------------
    def block(self, elems: Sequence[ET.Element], anchor: str | None) -> _Block:
        """Render a statement sequence inside the current (sub)graph.

        Comments attach to the previous flow node (``anchor`` for leading ones,
        when given) or else to the next flow node; comments of a block without
        flow statements are returned for the caller to place.
        """
        entry: str | None = None
        current: _Exit | None = None
        last = anchor
        pending: list[ET.Element] = []
        for el in elems:
            if el.tag == "comment":
                if last is None:
                    pending.append(el)
                else:
                    self.comment(el, last)
                continue
            stmt = self.statement(el)
            for cel in pending:
                self.comment(cel, stmt.anchor)
            pending = []
            if entry is None:
                entry = stmt.entry
            if current is not None:
                self.connect(current, stmt.entry)
            current = stmt.exit
            last = stmt.exit.node
        return _Block(entry, current, pending)

    def branch(self, elems: Sequence[ET.Element], fallback: str) -> tuple[str | None, _Exit | None]:
        """Render a branch / loop body in its own invisible cluster.

        The cluster keeps the body contiguous, so nested structures never
        interleave.  Comments of an otherwise empty body attach to ``fallback``.
        """
        if not any(el.tag != "comment" for el in elems):
            for el in elems:
                self.comment(el, fallback)
            return None, None
        self.open_cluster(style="invis", margin=6)
        result = self.block(elems, None)
        self.close_cluster()
        return result.entry, result.exit

    def statement(self, el: ET.Element) -> _Stmt:
        tag = el.tag
        if tag == "declare":
            nid = self.node("declare", _declare_label(el))
        elif tag == "assign":
            nid = self.node("assign", f"{el.get('variable', '')} = {el.get('expression', '')}")
        elif tag == "input":
            nid = self.node("input", f"Input {el.get('variable', '')}")
        elif tag == "output":
            nid = self.node("output", f"Output {el.get('expression', '')}")
        elif tag == "call":
            nid = self.node("call", f"Call {el.get('expression', '')}")
        elif tag == "breakpoint":
            nid = self.node("breakpoint", "Breakpoint")
        elif tag == "if":
            return self.if_statement(el)
        elif tag in ("while", "for"):
            return self.pre_test_loop(el)
        elif tag == "do":
            return self.post_test_loop(el)
        else:
            nid = self.node("unknown", _unknown_label(el))
        return _Stmt(nid, _Exit(nid), nid)

    def if_statement(self, el: ET.Element) -> _Stmt:
        cond = self.node("if", el.get("expression", ""))
        merge = self.point()
        then_el, else_el = el.find("then"), el.find("else")
        # False branch first and out of the west port, True branch out of the
        # east port: dot's crossing minimisation keeps west-port heads left of
        # east-port heads, which is Flowgorithm's False-left / True-right.
        for kids, port, label, angle in ((else_el, "w", "False", -30), (then_el, "e", "True", 30)):
            entry, exit_ = self.branch(list(kids) if kids is not None else [], cond)
            if entry is None:
                self.edge(f"{cond}:{port}", merge, taillabel=label, labelangle=angle,
                          arrowhead="none", weight=JOIN_WEIGHT)
            else:
                self.edge(f"{cond}:{port}", entry, taillabel=label, labelangle=angle, weight=FLOW_WEIGHT)
                self.connect(exit_, merge, arrowhead="none", weight=JOIN_WEIGHT)
            if port == "w":
                # Invisible spine between the branches: keeps the merge point
                # (and so the following flow) centred under the diamond.  The
                # explicit south port matters: dot orders a node's out-edges by
                # port position, so :w < :s < :e puts the spine in the middle.
                self.edge(f"{cond}:s", merge, style="invis", weight=SPINE_WEIGHT)
        return _Stmt(cond, _Exit(merge), cond)

    def pre_test_loop(self, el: ET.Element) -> _Stmt:
        text = _for_label(el) if el.tag == "for" else el.get("expression", "")
        hexagon = self.node("loop", text)
        entry, exit_ = self.branch(list(el), hexagon)
        if entry is None:  # empty body: True is a self-loop, False leaves at the bottom
            self.edge(f"{hexagon}:e", f"{hexagon}:e", label="True")
            return _Stmt(hexagon, _Exit(hexagon, "s", "False"), hexagon)
        done = self.point()
        self.edge(f"{hexagon}:w", done, taillabel="False", labelangle=-30, arrowhead="none",
                  weight=JOIN_WEIGHT)
        self.edge(f"{hexagon}:s", entry, taillabel="True", labelangle=30, weight=FLOW_WEIGHT)
        back: dict[str, object] = {"dir": "back", "weight": JOIN_WEIGHT}
        if exit_.label:
            back["headlabel"] = exit_.label
        self.edge(f"{hexagon}:e", exit_.ref, **back)
        # Invisible edge: ranks the exit point below the body and keeps it under it.
        self.edge(exit_.node, done, style="invis", weight=SPINE_WEIGHT)
        return _Stmt(hexagon, _Exit(done), hexagon)

    def post_test_loop(self, el: ET.Element) -> _Stmt:
        hexagon = self.node("loop", el.get("expression", ""))
        entry, exit_ = self.branch(list(el), hexagon)
        if entry is None:
            self.edge(f"{hexagon}:e", f"{hexagon}:e", label="True")
            return _Stmt(hexagon, _Exit(hexagon, "s", "False"), hexagon)
        self.connect(exit_, hexagon)
        self.edge(f"{entry}:e", f"{hexagon}:e", dir="back", headlabel="True", weight=JOIN_WEIGHT)
        # The entry node sits inside the body cluster, so comments preceding the
        # loop hang off the hexagon (which is in the enclosing cluster) instead.
        return _Stmt(entry, _Exit(hexagon, "s", "False"), hexagon)

    # -- functions ------------------------------------------------------------
    def function(self, fel: ET.Element) -> None:
        start_label, end_label = _function_labels(fel)
        name = fel.get("name", "") or f"function {self._clusters + 1}"
        self.open_cluster(label=name, labeljust="l", style="rounded", color="#B0B0B0",
                          fontcolor="#555555", margin=14)
        start = self.node("terminal", start_label)
        body = fel.find("body")
        result = self.block(list(body) if body is not None else [], start)
        for cel in result.comments:
            self.comment(cel, start)
        end = self.node("terminal", end_label)
        if result.entry is None or result.exit is None:
            self.edge(start, end, weight=FLOW_WEIGHT)
        else:
            self.edge(start, result.entry, weight=FLOW_WEIGHT)
            self.connect(result.exit, end)
        self.close_cluster()


# --------------------------------------------------------------------------- public API

def _parse(xml_text: str | bytes) -> ET.Element:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FprgError(f"not well-formed XML: {exc}") from None
    if root.tag != "flowgorithm":
        raise FprgError(f"root element is <{root.tag}>, expected <flowgorithm>")
    return root


def _program_name(root: ET.Element) -> str:
    attrs = root.find("attributes")
    if attrs is not None:
        for a in attrs.findall("attribute"):
            if a.get("name") == "name":
                return (a.get("value") or "").strip()
    return ""


def _functions(root: ET.Element, function: str | None) -> list[ET.Element]:
    funcs = root.findall("function")
    if not funcs:
        raise FprgError("no <function> elements found")
    funcs.sort(key=lambda f: 0 if (f.get("name") or "").lower() == "main" else 1)  # stable
    if function is None:
        return funcs
    chosen = [f for f in funcs if (f.get("name") or "").lower() == function.lower()]
    if not chosen:
        names = ", ".join(f.get("name") or "?" for f in funcs)
        raise FprgError(f"function {function!r} not found (available: {names})")
    return chosen


def fprg_to_dot(xml_text: str | bytes, function: str | None = None, *,
                wrap: int = DEFAULT_WRAP, splines: str = DEFAULT_SPLINES) -> str:
    """Convert Flowgorithm XML to Graphviz DOT.

    ``function`` selects a single function by (case-insensitive) name; by
    default every function is rendered as its own cluster, Main first.
    ``wrap`` soft-wraps labels longer than that many characters (0 disables).
    Raises :class:`FprgError` for malformed input or an unknown function.
    """
    root = _parse(xml_text)
    funcs = _functions(root, function)
    builder = _DotBuilder(wrap)
    builder.emit(f"graph [rankdir=TB, splines={_q(splines)}, nodesep=0.4, ranksep=0.45, "
                 f"fontname={_q(FONT)}, fontsize=13, bgcolor=white, pad=0.3];")
    builder.emit(f'node [fontname={_q(FONT)}, fontsize=11, margin="0.16,0.07", penwidth=1.1, '
                 f'color="#555555"];')
    builder.emit(f'edge [fontname={_q(FONT)}, fontsize=9, fontcolor="#333333", color="#444444", '
                 f"arrowsize=0.7, penwidth=1.0, labeldistance=1.8, labelangle=-30];")
    title = _program_name(root)
    if title:
        builder.emit(f"label={_q(title)}; labelloc=t; fontcolor=\"#333333\";")
    for fel in funcs:
        builder.function(fel)
    return "digraph flowgorithm {\n" + "\n".join(builder.lines) + "\n}\n"


def find_dot(explicit: str | None = None) -> str | None:
    """Path of the Graphviz ``dot`` executable, or None."""
    if explicit:
        return explicit if os.path.isfile(explicit) else shutil.which(explicit)
    found = shutil.which("dot")
    if found:
        return found
    for candidate in DOT_CANDIDATES:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def render_dot(dot_text: str, output: str, fmt: str | None = None, dot_bin: str | None = None) -> None:
    """Run ``dot`` on ``dot_text`` writing ``output`` (``"-"`` = stdout).

    Raises ``FileNotFoundError`` when dot cannot be found and ``RuntimeError``
    (with dot's stderr) when it fails.
    """
    exe = find_dot(dot_bin)
    if not exe:
        raise FileNotFoundError("Graphviz 'dot' executable not found")
    fmt = fmt or os.path.splitext(output)[1].lstrip(".").lower() or "svg"
    cmd = [exe, f"-T{fmt}"]
    if output != "-":
        cmd += ["-o", output]
    proc = subprocess.run(cmd, input=dot_text.encode("utf-8"), capture_output=True)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip() or f"exit status {proc.returncode}"
        raise RuntimeError(f"dot -T{fmt} failed: {detail}")
    if proc.stderr.strip():
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
    if output == "-":
        sys.stdout.buffer.write(proc.stdout)
        sys.stdout.buffer.flush()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fprg2svg.py",
        description="Render a Flowgorithm .fprg flowchart with Graphviz.",
        epilog="Output format follows the -o extension (svg, png, pdf, dot, or anything dot "
               "accepts as -T<ext>). Default output: the input path with .svg (or .dot with --dot). "
               "Use '-o -' to write to stdout. Exit status 1: bad input; 2: dot missing or failed.")
    parser.add_argument("input", help="Flowgorithm .fprg file")
    parser.add_argument("-o", "--output", help="output file (extension selects the format)")
    parser.add_argument("-f", "--function", help="render only this function (case-insensitive)")
    parser.add_argument("--dot", action="store_true", help="write DOT source instead of rendering")
    parser.add_argument("--wrap", type=int, default=DEFAULT_WRAP, metavar="N",
                        help=f"soft-wrap labels longer than N characters, 0 = never (default {DEFAULT_WRAP})")
    parser.add_argument("--splines", default=DEFAULT_SPLINES, metavar="MODE",
                        help=f"Graphviz splines setting (default {DEFAULT_SPLINES}; e.g. polyline, curved)")
    parser.add_argument("--dot-bin", metavar="PATH", help="Graphviz dot executable to use")
    parser.add_argument("--list-functions", action="store_true", help="print the function names and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        with open(args.input, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(f"fprg2svg: cannot read {args.input}: {exc}", file=sys.stderr)
        return 1

    try:
        if args.list_functions:
            for fel in _functions(_parse(data), None):
                print(_function_labels(fel)[0])
            return 0
        dot_text = fprg_to_dot(data, args.function, wrap=args.wrap, splines=args.splines)
    except FprgError as exc:
        print(f"fprg2svg: {args.input}: {exc}", file=sys.stderr)
        return 1

    output = args.output
    ext = os.path.splitext(output)[1].lstrip(".").lower() if output and output != "-" else ""
    want_dot = args.dot or ext in ("dot", "gv")
    if not output:
        output = os.path.splitext(args.input)[0] + (".dot" if want_dot else ".svg")
        ext = "dot" if want_dot else "svg"
    if want_dot:
        if output == "-":
            sys.stdout.write(dot_text)
        else:
            with open(output, "w", encoding="utf-8") as fh:
                fh.write(dot_text)
        return 0

    try:
        render_dot(dot_text, output, ext or "svg", args.dot_bin)
    except FileNotFoundError:
        print("fprg2svg: Graphviz 'dot' was not found on PATH. Install Graphviz "
              "(e.g. `brew install graphviz`) or pass --dot-bin /path/to/dot.", file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(f"fprg2svg: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
