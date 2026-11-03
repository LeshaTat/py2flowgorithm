# flowgorithm — Flowgorithm's statements and functions for Python

`flowgorithm` provides Python versions of Flowgorithm's console statements and built-in
functions. Use it to run and test a program before generating its flowchart with the
[converter](../converter/README.md). The [examples](../examples/README.md) show complete programs.
The library was written with Claude Opus 5.5 (Anthropic) and GPT-6 Astra (OpenAI), like the rest
of this repository.

## Getting started

It is one file with nothing outside the standard library (`src/flowgorithm.py`). Copy it next
to your program and use Python 3.11 or newer; no installation is required.
Save this example as `hello.py` beside `flowgorithm.py`:

```python
from flowgorithm import Input, Output


def main():
    Output("Your name?")
    name = Input(str)
    Output("How old are you?")
    age = Input(int)
    Output("Hello ", name, ", next year you will be ", age + 1)


if __name__ == "__main__":
    main()
```

Run `python3 hello.py` (`py hello.py` on Windows). Enter `Ann` and `20`; the final line is
`Hello Ann, next year you will be 21`.

Optionally, `python3 install.py` from the repository root makes the library and converter
available from any folder for that Python (see [optional installation](../README.md#installpy)).
In a virtual environment, `python3 -m pip install -e library` from the repository root also
makes the library importable without copying it.

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

See [What can still differ](../converter/README.md#what-can-still-differ) for differences between
Python and Flowgorithm, and the [probe results](../converter/docs/probe/README.md) for the
observations and runtime environment used to check the library's behaviour.

## Testing a program

A program can be tested with `unittest`. The `console` context manager supplies one answer per
`Input()` call and captures `Output()` text. Save this as `test_hello.py` beside `hello.py`:

```python
import unittest

from flowgorithm import console
from hello import main


class HelloTest(unittest.TestCase):
    def test_greeting(self):
        with console("Ann", "20") as screen:
            main()
        self.assertEqual(
            screen.text,
            "Your name?\nHow old are you?\nHello Ann, next year you will be 21\n",
        )
```

Run `python3 -m unittest -v` from that folder. For a program that calls `Random`, supply fixed
values with `console(..., randoms=[4, 2])`. Missing answers or random values raise
`FlowgorithmError`, making unexpected extra input visible in a test.

Tests may also sit in the program file. The converter leaves `unittest` imports and test
classes out of the flowchart; see the [cinema example](../examples/lab1_cinema/README.md).

## Tests

To test the library itself, run `python3 -m unittest discover -s tests` from `library/`.
No installation is required. Run `python3 run_tests.py` from the repository root to include
the converter and examples, including the checks in
[`test_library_agreement.py`](../converter/tests/test_library_agreement.py) that compare the
library with the converter's interpreter.
