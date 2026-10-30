"""py2fprg - write Python, get Flowgorithm flowcharts (.fprg files).

Public API::

    from py2fprg import convert_source, convert_path

    xml = convert_source(python_code, name="demo")          # one module -> .fprg text
    outputs = convert_path("path/to/project_or_file.py")    # [(output_filename, xml), ...]
"""
from __future__ import annotations

import os
from typing import Optional

from .model import ConvertError, Program, Warning_
from .project import ProgramBuilder
from .writer import write_program

__version__ = "0.1.0"
__all__ = ["convert_source", "convert_path", "ConvertError", "ProgramBuilder", "write_program",
           "Program", "Warning_", "__version__"]


def convert_source(source: str, name: str = "program", *, title: str = "", author: str = "",
                   comments: bool = True, all_functions: bool = False, fileversion: str = "3.0",
                   metadata: bool = True, warnings: Optional[list] = None) -> str:
    """Convert a single Python module given as text; returns the .fprg XML."""
    b = ProgramBuilder(comments=comments, author=author, all_functions=all_functions)
    m = b.add_source(source, name, f"<{name}>")
    program = b.build(m, title=title)
    if warnings is not None:
        warnings.extend(b.warnings)
    return write_program(program, fileversion=fileversion, metadata=metadata)


def convert_path(path: str, *, entry: Optional[str] = None, title: str = "", author: str = "",
                 comments: bool = True, all_functions: bool = False, fileversion: str = "3.0",
                 metadata: bool = True, warnings: Optional[list] = None) -> list[tuple[str, str]]:
    """Convert a project directory (or one .py file with its sibling modules).

    Returns ``[(suggested_output_path, xml), ...]``, one entry per program found.
    """
    b = ProgramBuilder(comments=comments, author=author, all_functions=all_functions)
    path = os.path.abspath(path)
    if os.path.isdir(path):
        root = path
        b.discover(root)
        if entry:
            entries = [_find_entry(b, root, entry)]
        else:
            entries = b.entry_candidates()
            if not entries:
                raise ConvertError("no program found: no module has a main() function or an "
                                   "`if __name__ == \"__main__\":` block", None,
                                   "use --entry to name the module that should become Main", root)
    else:
        root = os.path.dirname(path)
        b.discover(root)
        entries = [_find_entry(b, root, path)]
    outputs = []
    for m in entries:
        program = b.build(m, title=title)
        out = os.path.splitext(m.path)[0] + ".fprg"
        outputs.append((out, write_program(program, fileversion=fileversion, metadata=metadata)))
    if warnings is not None:
        warnings.extend(b.warnings)
    return outputs


def _find_entry(b: ProgramBuilder, root: str, entry: str):
    entry_abs = os.path.abspath(entry if os.path.isabs(entry) or os.path.exists(entry) else os.path.join(root, entry))
    for m in b.modules.values():
        if m.name == entry or os.path.abspath(m.path) == entry_abs:
            return m
    for name, err in b.failed.items():
        if name == entry or os.path.abspath(err.filename or "") == entry_abs:
            raise err
    if os.path.isfile(entry_abs):  # a test file or ignored file named explicitly
        name = os.path.splitext(os.path.relpath(entry_abs, root))[0].replace(os.sep, ".")
        return b.add_file(entry_abs, name)
    raise ConvertError(f"entry module '{entry}' not found in {root}", None)
