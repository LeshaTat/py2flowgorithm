# flowgorithm — Flowgorithm's statements and functions for Python

The library a program imports to be written the Flowgorithm way. It provides console statements
and built-in functions with Flowgorithm's
behaviour, so running the Python program shows what its flowchart will show. The
[converter](../converter) turns such a program into the flowchart; the
[examples](../examples) show whole programs. The library was written with Claude Opus 5.5
(Anthropic) and GPT-6 Astra (OpenAI), like the rest of this repository.

It is one file with nothing outside the standard library (`src/flowgorithm.py`). Copy it next
to your program; no installation is required. Optionally, run `python3 install.py` at the
repository root to make the library and converter available from any folder for your Python
(see the [repository's README](../README.md)). In a virtual environment,
`pip install -e library` also makes the library importable without copying it.

```python
from flowgorithm import Input, Output


def main():
    Output("Your name?")
    name = Input(str)
    Output("How old are you?")
    age = Input(int)
    Output("Hello ", name, ", next year you will be ", age + 1)
```

## Console

| Python | Flowgorithm |
|---|---|
| `Output(a, b, ...)` | Output `a & b & ...`: the values joined without spaces |
| `Output(..., newline=False)` | Output with the newline unticked |
| `x = Input(int)` | Input into an Integer: only whole-number text (`3.0` is rejected) |
| `x = Input(float)`, `Input(str)`, `Input(bool)` | Input into a Real, a String (the default), a Boolean (`true` / `false`) |

Values are shown the way Flowgorithm shows them: `2`, not `2.0`; `true`, not `True`; Reals with
at most 15 significant digits (`7 / 3` shows as `2.33333333333333`, `0.1 + 0.2` as `0.3`);
`1E+16`.

Flowgorithm also keeps every Real it calculates to 15 significant digits. The functions below
round their results the same way, but Python's own `+ - * /` keep all the digits: in Flowgorithm
`0.1 + 0.2 == 0.3` is true, in Python it is false. Compare Reals with a tolerance
(`Abs(a - b) < 0.000001`) instead of `==`; the converter warns about `==` and `!=` on Reals.

## Functions

| Function | Result |
|---|---|
| `Abs(n)`, `Sgn(n)` | the absolute value; -1, 0 or 1 |
| `Int(n)` | the whole-number part, toward zero: `Int(-3.7)` is `-3` |
| `Sqrt`, `Sin`, `Cos`, `Tan`, `Arcsin`, `Arccos`, `Arctan`, `Ln`, `Log`, `Log10` | Reals (`Log` is the natural logarithm, like `Ln`) |
| `Len(s)`, `Char(s, i)` | the length of a String; its character at `i`, counting from 0 |
| `ToCode(c)`, `ToChar(n)` | the code of a character, and the character of a code |
| `ToInteger(text)`, `ToReal(text)` | a number read from text: `ToInteger("42")` is `42` |
| `ToString(n)`, `ToFixed(n, digits)` | a number (or true/false) as text, as Output shows it; with exactly `digits` decimals (at least 1), rounded half away from zero (`ToFixed(2.675, 2)` is `2.68`) |
| `Random(n)` | a whole number from 0 to n - 1 |
| `Size(xs)` | the number of elements of an array |
| `pi` | 3.141592653589793 |

Where Flowgorithm stops with an error — a bad input, an index out of range, `Sqrt(-1)`,
`ToInteger("1.5")` — these raise `FlowgorithmError`.

Flowgorithm does not document every run-time rule (how many digits a Real shows, how `ToFixed`
rounds a value exactly halfway, ...). Where the library had to guess is listed under
[What can still differ](../converter/README.md#what-can-still-differ); the probe flowcharts in
[`converter/docs/probe`](../converter/docs/probe) settle it with one run in Flowgorithm.

## Testing a program

A program is ordinary Python, so it can be tested with `unittest`, even in the same file (the
converter leaves test classes out of the flowchart). `console` plays the user:

```python
from flowgorithm import console

with console("3", "Ann", randoms=[4]) as screen:   # typed answers; values Random() returns
    book_seat(booked, names)
self.assertIn("Customer name?", screen.text)       # what Output showed
```

## Tests

`python3 -m unittest discover -s tests` in this folder. That the library gives
exactly what the converter's interpreter gives is tested in
`converter/tests/test_library_agreement.py`.
