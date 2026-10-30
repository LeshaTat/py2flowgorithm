"""Command line interface: python -m py2fprg PATH... [options]."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__, convert_file, program_files
from .model import ConvertError


def count_shapes(xml: str) -> int:
    import re
    return len(re.findall(r"<(declare|assign|input|output|if|while|do|for|call|comment|breakpoint)\b", xml))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="py2fprg",
        description="Turn a Python program written in the Flowgorithm dialect (with the flowgorithm library) "
                    "into a Flowgorithm .fprg flowchart.",
        epilog="A folder converts every program file in it (a .py file with `def main():`; test files and "
               "flowgorithm.py are skipped). The .fprg goes next to each program. A program with an error is "
               "reported and the others are still converted.")
    p.add_argument("paths", nargs="+", metavar="path", help="a program file, or a folder of program files")
    p.add_argument("-o", "--output", help="output .fprg file (one program) or folder")
    p.add_argument("--no-comments", action="store_true", help="do not turn # comments and docstrings into Comment shapes")
    p.add_argument("--title", default="", help="program name shown in Flowgorithm (default: docstring or file name)")
    p.add_argument("--author", default="", help="author attribute (default: current user)")
    p.add_argument("--fileversion", default="3.0", help="fileversion attribute to write (default 3.0; 4.2 for Flowgorithm 4.x files)")
    p.add_argument("--no-metadata", action="store_true", help="omit saved/created/edited bookkeeping attributes")
    p.add_argument("--check", action="store_true", help="only check convertibility; write nothing")
    p.add_argument("--lint", action="store_true",
                   help="validate the generated file(s) with fprg_lint.py (declared-before-use, expression syntax, ...)")
    p.add_argument("--svg", action="store_true",
                   help="also render a preview next to each .fprg with fprg2svg.py (needs Graphviz)")
    p.add_argument("--stdout", action="store_true", help="print the .fprg XML instead of writing files")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress warnings")
    p.add_argument("--version", action="version", version=f"py2fprg {__version__}")
    a = p.parse_args(argv)

    files: list[str] = []
    failed = 0
    for path in a.paths:
        try:
            files += program_files(path)
        except ConvertError as e:
            print(e.format(), file=sys.stderr)
            failed += 1
    if a.output and a.output.lower().endswith(".fprg") and len(files) > 1:
        p.error(f"-o {a.output} names one file, but there are {len(files)} programs; give a folder")
    outputs = []
    for f in files:
        warnings: list = []
        error = None
        try:
            xml = convert_file(f, title=a.title, author=a.author, comments=not a.no_comments,
                               fileversion=a.fileversion, metadata=not a.no_metadata, warnings=warnings)
        except ConvertError as e:
            error = e
        if not a.quiet:
            for w in warnings:
                print(w.format(), file=sys.stderr)
        if error is not None:
            print(error.format(), file=sys.stderr)
            failed += 1
            continue
        outputs.append((os.path.splitext(f)[0] + ".fprg", xml))
    if failed and len(files) > 1:
        print(f"{len(outputs)} of {len(files)} programs converted", file=sys.stderr)
    rc = 1 if failed else 0
    if a.lint:
        rc = max(rc, lint_outputs(outputs, a.quiet))
    if a.check:
        for out, xml in outputs:
            print(f"ok: {os.path.basename(out)} ({count_shapes(xml)} shapes)")
        return rc
    for out, xml in outputs:
        if a.stdout:
            sys.stdout.write(xml)
            continue
        if a.output:
            if a.output.lower().endswith(".fprg") and len(outputs) == 1:
                out = a.output
            else:
                os.makedirs(a.output, exist_ok=True)
                out = os.path.join(a.output, os.path.basename(out))
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(xml)
        print(f"wrote {out} ({xml.count('<function ')} functions, {count_shapes(xml)} shapes)")
        if a.svg:
            rc = max(rc, render_svg(out, xml))
    return rc


def _tool(name: str):
    """Import a sibling helper script (fprg_lint / fprg2svg) that lives next to the package."""
    import importlib
    try:
        return importlib.import_module(name)
    except ImportError:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if here not in sys.path:
            sys.path.insert(0, here)
            try:
                return importlib.import_module(name)
            except ImportError:
                pass
    return None


def lint_outputs(outputs, quiet: bool) -> int:
    lint = _tool("fprg_lint")
    if lint is None:
        print("fprg_lint.py not found; skipping --lint", file=sys.stderr)
        return 0
    rc = 0
    for out, xml in outputs:
        findings = lint.lint_string(xml, os.path.basename(out))
        errors = [f for f in findings if f.severity == "ERROR"]
        for f in findings:
            if f.severity == "ERROR" or not quiet:
                print(str(f), file=sys.stderr)
        print(f"lint {os.path.basename(out)}: {len(errors)} errors, {len(findings) - len(errors)} warnings")
        if errors:
            rc = 1
    return rc


def render_svg(fprg_path: str, xml: str) -> int:
    render = _tool("fprg2svg")
    if render is None:
        print("fprg2svg.py not found; skipping --svg", file=sys.stderr)
        return 0
    svg_path = os.path.splitext(fprg_path)[0] + ".svg"
    try:
        render.render_dot(render.fprg_to_dot(xml), svg_path)
    except Exception as e:  # Graphviz missing, dot failure, ...
        print(f"could not render {svg_path}: {e}", file=sys.stderr)
        return 1
    print(f"wrote {svg_path}")
    return 0
