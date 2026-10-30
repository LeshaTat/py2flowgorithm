# py2fprg — solve the Flowgorithm problem in Python first

[Flowgorithm](http://www.flowgorithm.org) programs are drawn as flowcharts, shape by shape.
With py2fprg a student writes the program in Python instead — in a small dialect that matches
Flowgorithm one to one, using the `flowgorithm` library for Flowgorithm's input/output and
built-in functions — runs and tests it like any Python program, and gets the flowchart from it.

```python
"""Sum of Numbers.

Adds up the numbers from 1 to n."""
from flowgorithm import *


def total_to(n: int) -> int:
    total = 0
    for i in range(1, n + 1):
        total = total + i
    return total


def main():
    Output("How many numbers?")
    n = Input(int)
    Output("The sum is ", total_to(n))


if __name__ == "__main__":
    main()
```

```bash
python3 sum.py                      # run it: behaves like the flowchart will
python3 -m py2fprg sum.py           # -> sum.fprg, open it in Flowgorithm
```

The library makes Python behave like Flowgorithm, so the console shows the same text in both:
`Output` joins its values like `&` and prints numbers the way Flowgorithm does (`2`, not `2.0`;
`true`, not `True`), `Input(int)` reads like Flowgorithm's Input shape, `Int`, `ToFixed`, `Char`,
`Random`, ... work like Flowgorithm's functions. Everything outside the dialect is reported with
the file, the line and what to write instead (`print()` → use `Output(...)`).

## Getting started

Everything is standard-library Python 3.11+.

* `pip install -e .` in this folder installs the `py2fprg` command and the `flowgorithm` library;
  or just copy `flowgorithm.py` next to the program.
* `python3 -m py2fprg program.py` writes `program.fprg` next to it;
  `python3 -m py2fprg exercises/` converts every program file in a folder (a `.py` file with
  `def main():`; test files and `flowgorithm.py` are skipped).
* `--check` only checks the program, `--lint` validates the generated file, `--svg` draws a
  preview with Graphviz, `--stdout` prints the XML, `-o` names the output.

## The program

Every program has the same structure:

```python
"""Title of the program.

What it does: this becomes the program's description in Flowgorithm."""
from flowgorithm import *

MAX_TRIES = 5                        # constants: literal values (copied into the functions using them)


def helper(a: int, name: str) -> float:   # functions: typed parameters
    """A docstring becomes a comment."""
    ...
    return value                     # `return value` is the last statement (or no return at all)


def main():                          # the program itself: Flowgorithm's Main
    ...


if __name__ == "__main__":
    main()
```

Tests go into their own files (`test_*.py`) and are never converted.

## The dialect

| Python | Flowgorithm |
|---|---|
| `Output("Total: ", total)` | Output `"Total: " & total` |
| `Output("Name? ", newline=False)` | Output with the newline unticked |
| `n = Input(int)`, `Input(float)`, `Input(str)`, `Input(bool)` | Input into an Integer / Real / String / Boolean variable |
| `x = 5`, `x = 2.5`, `x: float = 0`, `x += 1` | Declare (at the top, one per type) + Assign |
| `xs = [0] * n`, `[0.0] * n`, `[""] * n`, `[False] * n`, `xs: list[int] = [0] * n` | Declare an array of size `n` |
| `xs = [3, 1, 2]` | Declare an array of size 3 + Assign each element |
| `xs[i] = value`, `xs[i] = Input(int)` | Assign / Input into an element |
| `if ...: elif ...: else:` | If (an elif is an If in the False branch) |
| `while condition:` | While |
| `while True:` ... `if condition: break` (the break-if is the last statement) | Do, repeating while `not condition` |
| `for i in range(n)`, `range(a, b)`, `range(a, b, -1)` | For `i` from `a` to `b - 1` (the step is a number; negative counts down) |
| `def f(a: int) -> float:` ... `return value` | a function with its return variable |
| `f(x)` as a statement | Call |
| `# comment`, docstrings | Comment |
| `# fg: ignore` on / above a statement or a `def` | left out of the flowchart (test helpers, debugging) |
| `# fg: breakpoint`, `breakpoint()` | Breakpoint |
| `# fg: comment text`, `# fg: name Title`, `# fg: about ...`, `# fg: author ...` | a Comment shape; the program's attributes |

Expressions:

| Python | Flowgorithm |
|---|---|
| `42`, `2.5`, `"text"`, `True`, `False`, `pi` | the same (`true`, `false`) |
| `+ - * / %`, `a ** b`, `-x` | `+ - * / %`, `a ^ b`, `-x` (`/` always gives a Real; `a ** b` is an Integer only for a whole-number exponent written out, like `n ** 2`) |
| `"Hello " + name`, `"n = " + ToString(n)` | `"Hello " & name` (`+` joins Strings; numbers go through `ToString`) |
| `==  !=  <  <=  >  >=`, `and  or  not` | the same (one comparison at a time; `and`/`or`/`not` need true/false) |
| `xs[i]`, `Size(xs)`, `Len(s)`, `Char(s, i)` | the same (indexes count from 0) |
| `Abs Arccos Arcsin Arctan Cos Int Ln Log Log10 Random Sgn Sin Sqrt Tan ToChar ToCode ToFixed ToInteger ToReal ToString` | the same intrinsic functions |
| `ToInteger("42")`, `ToReal("2.5")`, `ToString(n)` | as Flowgorithm documents them: the first two read text, `ToString` writes a number (`Int(x)` cuts off a fraction) |

Types: a variable gets its type from its first value (or an annotation like `total: float = 0`)
and keeps it. An Integer may go into a Real variable, not the other way round: `total = 0`
followed by `total = total + 0.5` is reported (write `total = 0.0`). Parameters are annotated
(`int`, `float`, `str`, `bool`, `list[int]` ...); a function's return type comes from its
annotation or from its `return` statement.

### Why some Python is rejected

The dialect only contains what Flowgorithm can draw, so that the Python program and the flowchart
do the same thing:

* Flowgorithm functions end by returning their result variable: `return` is the last statement.
  Set a variable in the branches instead of returning early.
* Loops have no `break`/`continue`, apart from the Do loop pattern above.
* A For loop counts with its variable: the body must not change it; nested loops use different
  variables; there is no `for x in list` (write `for i in range(Size(xs))`).
* After the loop Flowgorithm's counter is one step past Python's last value (`for i in range(3)`
  leaves `i` at 3, not 2), so the variable gets a new value before it is read again — also in the
  next round of a loop around it. Keep a value you need in another variable inside the loop.
* Python fixes where `range()` ends when the loop starts, so the body must not change what the
  end is computed from (`for i in range(n)` with `n = n - 1` inside is reported; `Size(xs)` is
  fine, an array keeps its size).
* `Input(...)` names the type of the variable it reads into (`x = Input(float)` for a Real `x`),
  because Flowgorithm's Input reads whatever its variable holds.
* Arrays have a fixed size and start out as 0 / 0.0 / "" / false; arrays are not copied or
  returned.
* There is no `//` (write `Int(a / b)`), no f-strings (pass several values to `Output`), no
  `print`/`input`/`len`/`int`/`str` (use the library), no methods, slices, tuples, dictionaries,
  classes, `import`s other than the library, and no code at the top level other than constants.

One difference remains: for negative numbers `%` gives different results (Python `-7 % 2` is `1`,
Flowgorithm's is `-1`).

## Testing a program

The program is ordinary Python, so it can be tested with `unittest`: call its functions, and play
whole runs with scripted answers by patching `builtins.input` (what `Input` reads with) and
`random.randrange` (what `Random` uses). See `examples/arith_quiz/test_quiz.py`.

## Checking the flowchart without Flowgorithm

* `fprg_lint.py file.fprg` — a strict validator for `.fprg` files (structure, identifiers,
  declared-before-use, Flowgorithm's expression grammar, light type checks).
* `fprg2svg.py file.fprg -o file.svg` — draws the flowchart with Graphviz.
* `fprg_run.py file.fprg --input 7 --random 3,5` — a headless interpreter for `.fprg` files. The
  tests use it to run each program both ways: the Python program with the library and its
  flowchart must print exactly the same text.
* The browser viewer [FlowgorithmJS](https://andreaval.github.io/FlowgorithmJS/drawLocal.html)
  opens the generated files too; Flowgorithm itself (Windows, or the macOS port
  [jostasik/Flowgorithm-macOS](https://github.com/jostasik/Flowgorithm-macOS)) is the final proof.

## The examples

* `examples/guess_number.py` — the classic guessing game: a Do loop, `elif`, a function, a constant.
* `examples/arith_quiz/quiz.py` — an arithmetic quiz with input validation, arrays, Random and
  several functions, and its tests in `examples/arith_quiz/test_quiz.py`
  (`cd examples/arith_quiz && python3 -m unittest -v`).

The `.fprg` files next to them are the converter's output.

## Files

| Path | What |
|---|---|
| `flowgorithm.py` | the library student programs import |
| `py2fprg/` | the converter (`program.py` the file structure, `convert.py` statements and expressions, `layout.py` comments and `# fg:` directives, `model.py` the shapes, `writer.py` the XML, `cli.py`) |
| `fprg_lint.py`, `fprg2svg.py`, `fprg_run.py` | validator, renderer, interpreter for `.fprg` files |
| `docs/fprg-format.md` | the reverse-engineered file format |
| `tests/` | tests for the library, the converter and the tools (`python3 -m unittest discover -s tests`) |
