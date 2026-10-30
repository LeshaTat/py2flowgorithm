"""py2fprg - turn a Python program written in the Flowgorithm dialect into a Flowgorithm flowchart.

The program uses the `flowgorithm` library (Output, Input, Len, ToInteger, ...) and has one fixed
structure (see README). Public API::

    from py2fprg import convert_source, convert_file, convert_path

    xml = convert_source(python_code)                     # the .fprg text
    xml = convert_file("exercise1.py")
    outputs = convert_path("exercises/")                  # [(output_path, xml), ...] for a folder
"""
from __future__ import annotations

import os
from typing import Optional

from .model import ConvertError, Program, Warning_
from .program import ProgramBuilder
from .writer import write_program

__version__ = "0.2.0"
__all__ = ["convert_source", "convert_file", "convert_path", "program_files", "ConvertError", "ProgramBuilder",
           "write_program", "Program", "Warning_", "__version__"]

SKIP_FILES = {"flowgorithm.py", "conftest.py", "setup.py"}


def convert_source(source: str, name: str = "program", *, title: str = "", author: str = "",
                   comments: bool = True, fileversion: str = "3.0", metadata: bool = True,
                   warnings: Optional[list] = None, path: str = "") -> str:
    """Convert one program given as text; returns the .fprg XML."""
    b = ProgramBuilder(source, path or f"<{name}>", comments=comments, author=author)
    try:
        program = b.build(title=title)
    finally:
        if warnings is not None:
            warnings.extend(b.warnings)
    return write_program(program, fileversion=fileversion, metadata=metadata)


def convert_file(path: str, **kw) -> str:
    """Convert one program file; returns the .fprg XML."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            source = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        raise ConvertError(f"cannot read the file: {e}", None, "save it as UTF-8", path) from None
    return convert_source(source, os.path.splitext(os.path.basename(path))[0], path=path, **kw)


def is_program_file(path: str) -> bool:
    """A .py file with `def main():` that is not a test file or the library itself."""
    name = os.path.basename(path)
    if not name.endswith(".py") or name in SKIP_FILES or name.startswith("test_") or name.endswith("_test.py"):
        return False
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return "def main(" in fh.read()
    except (OSError, UnicodeDecodeError):
        return False


def program_files(path: str) -> list[str]:
    """The program file itself, or the program files of a folder (not in sub-folders)."""
    if not os.path.isdir(path):
        return [path]
    files = sorted(os.path.join(path, f) for f in os.listdir(path) if is_program_file(os.path.join(path, f)))
    if not files:
        raise ConvertError("no program files here (a .py file with `def main():`)", None, filename=path)
    return files


def convert_path(path: str, **kw) -> list[tuple[str, str]]:
    """Convert a program file, or every program file in a folder (not in sub-folders).

    Returns ``[(output_path, xml), ...]``; the output goes next to the program (``.fprg``).
    """
    return [(os.path.splitext(f)[0] + ".fprg", convert_file(f, **kw)) for f in program_files(path)]
