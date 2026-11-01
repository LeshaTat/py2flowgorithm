# py2fprg — from a Python program to a Flowgorithm flowchart

`py2fprg` turns a Python program written in the Flowgorithm dialect into its Flowgorithm
flowchart (`.fprg`), shape for shape. The programs use the [`flowgorithm` library](../library) for
Flowgorithm's input/output and built-in functions, so running one in Python shows what its
flowchart will show; the [examples](../examples) are such programs. Everything outside the dialect
is reported with the file, the line and what to write instead (`print()` → use `Output(...)`).

The package also has three tools for `.fprg` files: a validator, a renderer and an interpreter
(see [Checking the flowchart without Flowgorithm](#checking-the-flowchart-without-flowgorithm)).

## Getting started

`python3 install.py` at the repository root installs the converter and the library for your
Python (see the [repository's README](../README.md)): the commands `py2fprg`, `fprg-lint`,
`fprg2svg` and `fprg-run` then work in any folder, as does `python3 -m py2fprg`. In a virtual
environment, `pip install -e converter` works too; without installing, run
`PYTHONPATH=converter/src python3 -m py2fprg`.

* `py2fprg program.py` writes `program.fprg` next to it; `py2fprg exercises/` converts every
  program file in a folder (a `.py` file with `def main():`; test files and `flowgorithm.py` are
  skipped). Several files and folders can be given at once; a program with an error is reported
  and the others are still converted.
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
  returned, and are made once, outside loops (Flowgorithm declares them where they are made).
* There is no `//` (write `Int(a / b)`), no f-strings (pass several values to `Output`), no
  `print`/`input`/`len`/`int`/`str` (use the library), no methods, slices, tuples, dictionaries,
  classes, `import`s other than the library, and no code at the top level other than constants.

### What can still differ

Flowgorithm's run-time rules are not all documented, so the converter warns where it can; the
probe flowcharts in [`docs/probe/`](docs/probe) settle these in real Flowgorithm:

* `%` with a negative left side: Flowgorithm stops the program ("Illegal Value: The value '-7'
  is not valid for the function % mod"), Python gives a result (`-7 % 2` is `1`). Keep the left
  side of `%` at 0 or more (the converter rejects a negative number written out).
* `and` / `or`: Python skips the right side when the left side decides; Flowgorithm may evaluate
  both. `while i < Size(xs) and xs[i] != x` is warned about: the index must also work when
  `i < Size(xs)` is false, so test it in a nested if (or use a found flag, as in
  [`examples/exercises/search.py`](../examples/exercises/search.py)).
* Ordering Strings with `<` / `>` (warned about): Python compares character codes (`"B" < "a"`),
  Flowgorithm may order upper and lower case differently. `==` and `!=` are the same.
* Reals that do not end, like `7 / 3`: the library prints all the digits Python has
  (`2.3333333333333335`), an older Flowgorithm may print fewer. Show such results with
  `ToFixed(x, 2)`. `ToFixed` of a value exactly halfway (`ToFixed(2.25, 1)`) may round the other
  way.
* Very large whole numbers: Python's Integers have no limit, Flowgorithm's have a fixed size
  (keep them below 2 147 483 647, or use a Real).

## Checking the flowchart without Flowgorithm

* `fprg-lint file.fprg` (`fprg_lint.py`) — a strict validator for `.fprg` files (structure,
  identifiers, declared-before-use, Flowgorithm's expression grammar, light type checks).
* `fprg2svg file.fprg -o file.svg` (`fprg2svg.py`) — draws the flowchart with Graphviz.
* `fprg-run file.fprg --input 7 --random 3,5` (`fprg_run.py`) — a headless interpreter for
  `.fprg` files. The tests use it to run each program both ways: the Python program with the
  library and its flowchart must print exactly the same text.
* The browser viewer [FlowgorithmJS](https://andreaval.github.io/FlowgorithmJS/drawLocal.html)
  opens the generated files too; Flowgorithm itself (Windows, or the macOS port
  [jostasik/Flowgorithm-macOS](https://github.com/jostasik/Flowgorithm-macOS)) is the final proof.
* `docs/probe/` — a flowchart that shows, run in real Flowgorithm, the run-time rules
  the library and `fprg_run.py` had to guess (how Reals are printed, `ToFixed` rounding, `%`,
  `and`/`or`, String order, the For counter, array start values, Integer size). Its README says
  what each output line means and lists the answers found so far.

## Files

| Path | What |
|---|---|
| `src/py2fprg/` | the converter (`program.py` the file structure, `convert.py` statements and expressions, `layout.py` comments and `# fg:` directives, `model.py` the shapes, `writer.py` the XML, `cli.py`) |
| `src/fprg_lint.py`, `src/fprg2svg.py`, `src/fprg_run.py` | validator, renderer, interpreter for `.fprg` files |
| `docs/fprg-format.md` | the reverse-engineered file format |
| `docs/probe/` | flowcharts that show Flowgorithm's undocumented run-time rules when run (`make_probe.py` builds them) |
| `tests/` | tests for the converter and the tools, and that the library agrees with `fprg_run` (`python3 -m unittest discover -s tests` in this folder) |
