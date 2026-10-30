"""Core data model for py2fprg: Flowgorithm types, shapes (IR), errors, identifiers."""
from __future__ import annotations

import ast
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional, Union

# --------------------------------------------------------------------------- #
# Types
# --------------------------------------------------------------------------- #
INTEGER, REAL, STRING, BOOLEAN = "Integer", "Real", "String", "Boolean"
VOID = "None"
SCALARS = (INTEGER, REAL, STRING, BOOLEAN)


@dataclass(frozen=True)
class ArrayT:
    elem: str

    def __str__(self) -> str:
        return f"{self.elem}[]"


# A resolved Flowgorithm type: a scalar name, an ArrayT, or None when unknown.
FgType = Union[str, ArrayT, None]

PY_SCALAR = {"int": INTEGER, "float": REAL, "str": STRING, "bool": BOOLEAN}
PY_NAME_OF = {INTEGER: "int", REAL: "float", STRING: "str", BOOLEAN: "bool"}

RESERVED = {
    "and", "false", "mod", "not", "or", "pi", "true",
    "boolean", "integer", "real", "string", "none",
    "abs", "cos", "random", "tan", "tostring", "arccos", "int", "sgn", "tochar",
    "toreal", "arcsin", "len", "sin", "tocode", "arctan", "log", "size",
    "tofixed", "char", "log10", "sqrt", "tointeger", "ln", "eof",
    "arccosh", "cosh", "arcsinh", "sinh", "arctanh", "tanh",
    "main",  # only Main itself may use this name
}

# Flowgorithm operator precedence levels (higher binds tighter)
P_OR, P_AND, P_REL, P_CAT, P_ADD, P_MUL, P_POW, P_UNARY, P_ATOM = 1, 2, 3, 4, 5, 6, 7, 8, 9


def type_name(t: FgType) -> str:
    return "unknown" if t is None else str(t)


def join_types(a: FgType, b: FgType) -> FgType:
    """Least upper bound of two inferred types; raises TypeError on conflict."""
    if a is None:
        return b
    if b is None or a == b:
        return a
    if {a, b} == {INTEGER, REAL}:
        return REAL
    raise TypeError(f"{type_name(a)} and {type_name(b)}")


def is_numeric(t: FgType) -> bool:
    return t in (INTEGER, REAL)


# --------------------------------------------------------------------------- #
# Errors / warnings
# --------------------------------------------------------------------------- #
class ConvertError(Exception):
    """A construct that cannot be represented in Flowgorithm (reported with a location)."""

    def __init__(self, msg: str, node: Optional[ast.AST] = None, hint: str = "", filename: str = ""):
        super().__init__(msg)
        self.msg = msg
        self.hint = hint
        self.filename = filename
        self.lineno = getattr(node, "lineno", None)
        self.col = getattr(node, "col_offset", None)

    def format(self) -> str:
        loc = self.filename or "<source>"
        if self.lineno is not None:
            loc += f":{self.lineno}"
            if self.col is not None:
                loc += f":{self.col + 1}"
        text = f"{loc}: error: {self.msg}"
        if self.hint:
            text += f"\n    hint: {self.hint}"
        return text

    def __str__(self) -> str:
        return self.format()


@dataclass
class Warning_:
    msg: str
    filename: str = ""
    lineno: Optional[int] = None

    def format(self) -> str:
        loc = self.filename or "<source>"
        if self.lineno is not None:
            loc += f":{self.lineno}"
        return f"{loc}: warning: {self.msg}"


# --------------------------------------------------------------------------- #
# Intermediate representation = Flowgorithm shapes
# --------------------------------------------------------------------------- #
@dataclass
class Declare:
    names: list[str]
    type: str
    array: bool = False
    size: str = ""


@dataclass
class Assign:
    variable: str
    expression: str


@dataclass
class Input:
    variable: str


@dataclass
class Output:
    expression: str
    newline: bool = True


@dataclass
class If:
    expression: str
    then: list = field(default_factory=list)
    else_: list = field(default_factory=list)


@dataclass
class While:
    expression: str
    body: list = field(default_factory=list)


@dataclass
class Do:
    expression: str
    body: list = field(default_factory=list)


@dataclass
class For:
    variable: str
    start: str
    end: str
    direction: str = "inc"
    step: str = "1"
    body: list = field(default_factory=list)


@dataclass
class Call:
    expression: str


@dataclass
class Comment:
    text: str


@dataclass
class Breakpoint:
    pass


@dataclass
class Param:
    name: str
    type: str
    array: bool = False


@dataclass
class Function:
    name: str
    type: str = VOID
    variable: str = ""
    params: list[Param] = field(default_factory=list)
    body: list = field(default_factory=list)


@dataclass
class Program:
    name: str
    functions: list[Function]
    authors: str = ""
    about: str = ""


# --------------------------------------------------------------------------- #
# Identifier handling
# --------------------------------------------------------------------------- #
# Letters that Unicode decomposition does not reduce to ASCII (Python identifiers may use them).
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye", "ґ": "g",
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i",
}


def ascii_name(name: str) -> str:
    """Transliterate a (Unicode) Python identifier to ASCII: `größe` -> `grosse`, `счёт` -> `schet`."""
    out = []
    for ch in name:
        if ch.isascii():
            out.append(ch)
            continue
        low = ch.lower()
        if low in TRANSLIT:
            rep = TRANSLIT[low]
        else:
            rep = "".join(c for c in unicodedata.normalize("NFKD", ch) if c.isascii())
        if rep and ch != low:
            rep = rep[0].upper() + rep[1:]
        out.append(rep)
    return "".join(out)


def legalize(name: str) -> str:
    """Turn a Python identifier into a legal Flowgorithm identifier.

    snake_case -> camelCase, UPPER_SNAKE -> camelCase, non-ASCII letters are transliterated,
    leading digits get a prefix, reserved words get a ``Val`` suffix.  Uniqueness is handled by
    Namespace.
    """
    name = ascii_name(name)
    parts = [p for p in name.split("_") if p]
    if not parts:
        return "v"
    if name.isupper() and len(parts) > 1:  # MAX_TRIES -> maxTries (ADD stays ADD)
        parts = [p.lower() for p in parts]
    out = parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    out = re.sub(r"[^A-Za-z0-9]", "", out) or "v"
    if not out[0].isalpha():
        out = "v" + out
    if out.lower() in RESERVED:
        out += "Val"
    return out


class Namespace:
    """Case-insensitive set of taken identifiers (Flowgorithm identifiers are case-insensitive)."""

    def __init__(self, taken: Optional[set[str]] = None):
        self.taken: set[str] = {t.lower() for t in (taken or set())}

    def reserve(self, want: str) -> str:
        cand, n = want, 1
        while cand.lower() in self.taken or cand.lower() in RESERVED:
            n += 1
            cand = f"{want}{n}"
        self.taken.add(cand.lower())
        return cand

    def has(self, name: str) -> bool:
        return name.lower() in self.taken
