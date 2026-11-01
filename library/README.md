# flowgorithm — Flowgorithm's statements and functions for Python

The library a program imports to be written the Flowgorithm way. `from flowgorithm import *`
gives Flowgorithm's Output and Input statements and its built-in functions, with Flowgorithm's
behaviour, so running the Python program shows what its flowchart will show. The
[converter](../converter) turns such a program into the flowchart; the
[examples](../examples) show whole programs.

It is one file with nothing outside the standard library: install it with `pip install -e library`
(from the repository root), or copy `flowgorithm.py` next to the program.

```python
from flowgorithm import *


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

Values are shown the way Flowgorithm shows them: `2`, not `2.0`; `true`, not `True`; `1E+16`.

## Functions

| Function | Result |
|---|---|
| `Abs(n)`, `Sgn(n)` | the absolute value; -1, 0 or 1 |
| `Int(n)` | the whole-number part, toward zero: `Int(-3.7)` is `-3` |
| `Sqrt`, `Sin`, `Cos`, `Tan`, `Arcsin`, `Arccos`, `Arctan`, `Ln`, `Log`, `Log10` | Reals (`Log` is the natural logarithm, like `Ln`) |
| `Len(s)`, `Char(s, i)` | the length of a String; its character at `i`, counting from 0 |
| `ToCode(c)`, `ToChar(n)` | the code of a character, and the character of a code |
| `ToInteger(text)`, `ToReal(text)` | a number read from text: `ToInteger("42")` is `42` |
| `ToString(n)`, `ToFixed(n, digits)` | a number as text, as Output shows it; with exactly `digits` decimals |
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

A program is ordinary Python, so it can be tested with `unittest`: call its functions, and play
whole runs with scripted answers by patching `builtins.input` (what `Input` reads with) and
`random.randrange` (what `Random` uses). See
[`examples/arith_quiz/test_quiz.py`](../examples/arith_quiz/test_quiz.py).

## Tests

`python3 -m unittest discover -s library/tests` from the repository root. That the library gives
exactly what the converter's interpreter gives is tested in
`converter/tests/test_library_agreement.py`.
