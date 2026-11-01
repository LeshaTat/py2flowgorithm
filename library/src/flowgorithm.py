"""flowgorithm - write a Flowgorithm program in Python.

Put this file next to your program and start it with ``from flowgorithm import *``. You get
Flowgorithm's console statements and its built-in functions, with Flowgorithm's behaviour:

* ``Output(value, ...)`` prints like Flowgorithm's Output shape: the values joined without
  spaces (``Output("Total: ", total)`` is ``"Total: " & total``), numbers the way Flowgorithm
  shows them (``2``, not ``2.0``), Booleans as ``true`` / ``false``. ``newline=False`` keeps the
  cursor on the line.
* ``x = Input(int)`` reads one line like Flowgorithm's Input shape into an Integer; ``float``
  for Real, ``str`` for String, ``bool`` for Boolean (``true`` / ``false``).
* ``Abs Arccos Arcsin Arctan Char Cos Int Len Ln Log Log10 Random Sgn Sin Size Sqrt Tan ToChar
  ToCode ToFixed ToInteger ToReal ToString`` and ``pi`` work like Flowgorithm's intrinsic
  functions (``Int`` cuts off the fraction, ``Char(s, i)`` counts from 0, ``Random(n)`` gives
  0 .. n-1, ``ToFixed(x, 2)`` gives a String, ...).

For tests, ``with console("3", "Ann") as screen:`` runs code as if those answers were typed (and
``console(..., randoms=[4])`` makes Random() give 4); ``screen.text`` is what Output showed.

Running the Python program then shows what the flowchart will show, and ``py2fprg`` turns it
into the flowchart shape for shape. Where Flowgorithm would stop with an error (a bad input, an
index out of range, the square root of a negative number) these functions raise
``FlowgorithmError``.
"""
from __future__ import annotations

import contextlib as _contextlib
import decimal as _decimal
import io as _io
import math as _math
import random as _random
import re as _re

__all__ = ["Output", "Input", "Abs", "Arccos", "Arcsin", "Arctan", "Char", "Cos", "Int", "Len", "Ln",
           "Log", "Log10", "Random", "Sgn", "Sin", "Size", "Sqrt", "Tan", "ToChar", "ToCode", "ToFixed",
           "ToInteger", "ToReal", "ToString", "pi", "FlowgorithmError", "console"]

pi = _math.pi
_INT_TEXT = _re.compile(r"[+-]?[0-9]+")


class FlowgorithmError(Exception):
    """Something that stops a Flowgorithm program: a bad input, an index out of range, ..."""


def _text(value) -> str:
    """A value as Flowgorithm's Output, `&` and ToString show it."""
    t = type(value)
    if t is bool:
        return "true" if value else "false"
    if t is int:
        return str(value)
    if t is float:
        if value != value:
            return "NaN"
        if value in (_math.inf, -_math.inf):
            return "Infinity" if value > 0 else "-Infinity"
        if value == 0:
            return "0"
        # 15 significant digits, as Flowgorithm shows a Real (.NET Framework): 7 / 3 is 2.33333333333333,
        # 0.1 + 0.2 is 0.3, 1E+15, 1E-05
        return format(value, ".15g").replace("e", "E")
    if t is str:
        return value
    if isinstance(value, list):
        raise FlowgorithmError("an array cannot be output; output its elements one by one")
    raise FlowgorithmError(f"cannot output a value of type {t.__name__}")


def _real(value: float) -> float:
    """A Real result as Flowgorithm keeps it: rounded to 15 significant digits. Flowgorithm rounds
    every Real it computes; Python's own arithmetic cannot be made to, but these functions can."""
    return float(format(value, ".15g")) if _math.isfinite(value) else value


def _number(name: str, value):
    if type(value) not in (int, float):
        raise FlowgorithmError(f"{name}() needs a number, got {_text_or_type(value)}")
    return value


def _integer(name: str, value) -> int:
    if type(value) is not int:
        raise FlowgorithmError(f"{name}() needs an Integer, got {_text_or_type(value)}")
    return value


def _string(name: str, value) -> str:
    if type(value) is not str:
        raise FlowgorithmError(f"{name}() needs a String, got {_text_or_type(value)}")
    return value


def _text_or_type(value) -> str:
    return f"the {type(value).__name__} {value!r}"


# --------------------------------------------------------------------------- console
def Output(*values, newline: bool = True) -> None:
    """Flowgorithm's Output shape: the values joined like `&` (no spaces added)."""
    print("".join(_text(v) for v in values), end="\n" if newline else "", flush=True)


def Input(kind=str):
    """Flowgorithm's Input shape: read one line as an Integer (int), Real (float), String (str)
    or Boolean (bool). An Integer accepts only whole-number text, as in Flowgorithm."""
    line = input()
    if kind is str:
        return line
    s = line.strip()
    if kind is int:
        if _INT_TEXT.fullmatch(s):
            return int(s)
        raise FlowgorithmError(f"the input {line!r} is not an Integer")
    if kind is float:
        try:
            return float(s)
        except ValueError:
            raise FlowgorithmError(f"the input {line!r} is not a Real") from None
    if kind is bool:
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        raise FlowgorithmError(f"the input {line!r} is not a Boolean (true / false)")
    raise FlowgorithmError("Input() needs int, float, str or bool")


# --------------------------------------------------------------------------- math
def Abs(n):
    n = abs(_number("Abs", n))
    return _real(n) if type(n) is float else n


def Sgn(n) -> int:
    n = _number("Sgn", n)
    return (n > 0) - (n < 0)


def Int(n) -> int:
    """The whole-number part (toward zero): Int(3.7) is 3, Int(-3.7) is -3."""
    n = _number("Int", n)
    if type(n) is float and (n != n or n in (_math.inf, -_math.inf)):
        raise FlowgorithmError(f"Int() of {_text(n)}")
    return int(n)


def Sqrt(n) -> float:
    n = _number("Sqrt", n)
    if n < 0:
        raise FlowgorithmError(f"Sqrt() of a negative number ({_text(n)})")
    return _real(_math.sqrt(n))


def Sin(n) -> float:
    return _real(_math.sin(_number("Sin", n)))


def Cos(n) -> float:
    return _real(_math.cos(_number("Cos", n)))


def Tan(n) -> float:
    return _real(_math.tan(_number("Tan", n)))


def Arcsin(n) -> float:
    n = _number("Arcsin", n)
    if not -1 <= n <= 1:
        raise FlowgorithmError(f"Arcsin() argument {_text(n)} is outside -1..1")
    return _real(_math.asin(n))


def Arccos(n) -> float:
    n = _number("Arccos", n)
    if not -1 <= n <= 1:
        raise FlowgorithmError(f"Arccos() argument {_text(n)} is outside -1..1")
    return _real(_math.acos(n))


def Arctan(n) -> float:
    return _real(_math.atan(_number("Arctan", n)))


def _log(name: str, n, base10: bool = False) -> float:
    n = _number(name, n)
    if n <= 0:
        raise FlowgorithmError(f"{name}() of a non-positive number ({_text(n)})")
    return _real(_math.log10(n) if base10 else _math.log(n))


def Ln(n) -> float:
    """The natural logarithm."""
    return _log("Ln", n)


def Log(n) -> float:
    """The natural logarithm (as Flowgorithm's Log)."""
    return _log("Log", n)


def Log10(n) -> float:
    return _log("Log10", n, True)


# --------------------------------------------------------------------------- strings and conversion
def Len(s: str) -> int:
    """The number of characters of a String (Size() is for arrays)."""
    return len(_string("Len", s))


def Char(s: str, i: int) -> str:
    """The character at position i, counting from 0."""
    s, i = _string("Char", s), _integer("Char", i)
    if not 0 <= i < len(s):
        raise FlowgorithmError(f"Char() index {i} is out of range for a string of length {len(s)}")
    return s[i]


def ToChar(code: int) -> str:
    code = _integer("ToChar", code)
    if not 0 <= code <= 0x10FFFF:
        raise FlowgorithmError(f"ToChar() code {code} is not a valid character code")
    return chr(code)


def ToCode(s: str) -> int:
    s = _string("ToCode", s)
    if not s:
        raise FlowgorithmError("ToCode() of an empty string")
    return ord(s[0])


def ToFixed(n, decimals: int) -> str:
    """A String with exactly `decimals` digits after the point (at least 1): ToFixed(2.5, 2) is "2.50"."""
    n, decimals = _number("ToFixed", n), _integer("ToFixed", decimals)
    if decimals < 1:  # Flowgorithm: "The value '0' is not valid for the function ToFixed."
        raise FlowgorithmError(f"the value {decimals} is not valid for ToFixed(): it shows at least 1 digit "
                               "after the point")
    return _fixed(float(n), decimals)


def ToInteger(text: str) -> int:
    """A whole number from text: ToInteger("42") is 42 (Int(x) cuts off a number's fraction)."""
    text = _string("ToInteger", text)
    if _INT_TEXT.fullmatch(text.strip()):
        return int(text.strip())
    raise FlowgorithmError(f"ToInteger() cannot convert {text!r}")


def ToReal(text: str) -> float:
    """A number from text: ToReal("2.5") is 2.5."""
    text = _string("ToReal", text)
    try:
        return _real(float(text.strip()))
    except ValueError:
        raise FlowgorithmError(f"ToReal() cannot convert {text!r}") from None


def ToString(value) -> str:
    """A number or a Boolean as text, exactly as Output shows it: ToString(2.0) is "2"."""
    if type(value) not in (int, float, bool):
        raise FlowgorithmError(f"ToString() needs a number or a Boolean, got {_text_or_type(value)}")
    return _text(value)

def _fixed(value: float, digits: int) -> str:
    """ToFixed as Flowgorithm does it (.NET Framework's "F" format): the number to 15 significant
    digits, then rounded half away from zero to `digits` places: 2.675 gives 2.68, 2.25 gives 2.3."""
    if not _math.isfinite(value):
        return _text(value)
    with _decimal.localcontext() as context:
        context.prec = 1000
        exact = _decimal.Decimal(format(value, ".15g")).quantize(_decimal.Decimal(1).scaleb(-digits),
                                                                 rounding=_decimal.ROUND_HALF_UP)
    text = format(exact, "f")
    return text[1:] if text.startswith("-") and not exact else text  # no "-0.00"



# --------------------------------------------------------------------------- other
def Random(n: int) -> int:
    """A random Integer from 0 to n - 1."""
    n = _integer("Random", n)
    if n <= 0:
        raise FlowgorithmError(f"Random() needs a positive Integer, got {n}")
    return _random.randrange(n)


def Size(array: list) -> int:
    """The number of elements of an array (Len() is for strings)."""
    if not isinstance(array, list):
        raise FlowgorithmError(f"Size() needs an array, got {_text_or_type(array)}")
    return len(array)


# --------------------------------------------------------------------------- tests
class _Screen:
    """What Output showed while a console() was open, in `.text`."""

    def __init__(self) -> None:
        self.buffer = _io.StringIO()

    @property
    def text(self) -> str:
        return self.buffer.getvalue()


@_contextlib.contextmanager
def console(*answers: str, randoms=()):
    """For tests: run code as if the user typed `answers` (each Input() reads the next one) and
    Random() returned `randoms`; afterwards `.text` holds what Output showed.

        with console("3", "Ann") as screen:
            book_seat(booked, names)
        self.assertIn("Customer name?", screen.text)
    """
    from unittest import mock
    typed, rolls = iter(answers), iter(randoms)

    def read(prompt: str = "") -> str:
        try:
            return next(typed)
        except StopIteration:
            raise FlowgorithmError("the program asked for more answers than the test typed") from None

    def roll(n: int) -> int:
        try:
            return next(rolls) % n
        except StopIteration:
            raise FlowgorithmError("the program used more random numbers than the test gave") from None

    screen = _Screen()
    with mock.patch("builtins.input", side_effect=read), mock.patch("random.randrange", side_effect=roll), \
            _contextlib.redirect_stdout(screen.buffer):
        yield screen
