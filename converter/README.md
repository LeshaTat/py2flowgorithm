# py2fprg — from a Python program to a Flowgorithm flowchart

`py2fprg` turns a Python program written in the Flowgorithm dialect into its Flowgorithm
flowchart (`.fprg`), shape for shape. The programs use the [`flowgorithm` library](../library) for
Flowgorithm's input/output and built-in functions, so running one in Python shows what its
flowchart will show; the [examples](../examples) are such programs. Unsupported syntax is
reported with the file, line and a suggested alternative (`print()` → use `Output(...)`).

The conversion is one-way: nothing turns a `.fprg` back into Python, and converting again
overwrites the flowchart, so changes go into the program. The converter was written with Claude
Opus 5.5 (Anthropic) and GPT-6 Astra (OpenAI), like the rest of this repository.

The package also has three tools for `.fprg` files: a validator, a renderer and an interpreter
(see [Checking the flowchart without Flowgorithm](#checking-the-flowchart-without-flowgorithm)).

## Getting started

Use Python 3.11 or newer. No installation is required: from the repository root, run:

```bash
python3 py2fprg.py program.py
```

This writes `program.fprg` beside the source file. On Windows, use `py` in place of `python3`.
From another folder, use the full path to `py2fprg.py`. The launcher delegates to the converter
package in `converter/src/py2fprg/`; keep it in the checkout.

Conversion reads the source without running it. To run the Python program itself, copy
`library/src/flowgorithm.py` next to it.

Optionally, `python3 install.py` at the repository root makes the library and commands
`py2fprg`, `fprg-lint`, `fprg2svg` and `fprg-run` available from any folder for your Python
(see [optional installation](../README.md#installpy)). In a virtual environment,
`python3 -m pip install -e converter` from the repository root also installs the converter.

## Conversion options

These commands run from the repository root:

```bash
python3 py2fprg.py program.py --check            # check without writing a file
python3 py2fprg.py program.py --lint             # convert and validate the generated XML
python3 py2fprg.py program.py --svg              # also draw program.svg (requires Graphviz)
python3 py2fprg.py program.py -o output.fprg     # choose the output path
python3 py2fprg.py exercises/                   # convert programs directly inside a folder
```

Replace `program.py` and `exercises/` with your paths. Folder conversion selects `.py` files
with `def main():`, skipping test files and `flowgorithm.py`. It does not recurse into
subfolders. You can give several files or folders in one command; an error in one program
does not prevent conversion of the others.

`--stdout` prints the XML instead of writing a file. With multiple programs, `-o` names an
output folder. Run `python3 py2fprg.py --help` for all options. After optional installation,
`py2fprg` or `python3 -m py2fprg` can replace `python3 py2fprg.py`.

## The program

Programs have a `main()` function, optional helper functions and literal constants. This is
a complete example; save it as `tickets.py` and convert it with
`python3 py2fprg.py tickets.py` from the repository root:

```python
"""Ticket price.

Calculate the total price of a group booking."""
from flowgorithm import Input, Output, ToFixed

PRICE = 7.5


def total_price(tickets: int) -> float:
    """Multiply the ticket count by the price."""
    return tickets * PRICE


def main():
    Output("How many tickets?")
    tickets = Input(int)
    Output("Total: ", ToFixed(total_price(tickets), 2))


if __name__ == "__main__":
    main()
```

The module docstring supplies the title and description. Function parameters have type
annotations, and a value-returning function ends with `return`. `main()` becomes Flowgorithm's
Main function. The final `if` block runs it when the file is executed in Python.
For input `3`, this example prints `Total: 22.50` after its prompt.

A program can be split into several files: it imports functions and constants from files in its
folder (`from seats import seat_map`), and those files from others. A flowchart holds all its
functions, so the imported functions the program uses go into its one flowchart; only the file
with `main()` is a program (`py2fprg folder/` converts just those).

Tests can sit next to the code they test: `import unittest` and classes deriving from
`TestCase` are left out of the flowchart. Separate `test_*.py` files work too and are never
converted.

## The dialect

| Python | Flowgorithm |
|---|---|
| `Output("Total: ", total)` | Output `"Total: " & total` |
| `Output("Name? ", newline=False)` | Output with the newline unticked |
| `n = Input(int)`, `Input(float)`, `Input(str)`, `Input(bool)` | Input into an Integer / Real / String / Boolean variable |
| `x = 5`, `x = 2.5`, `x: float = 0`, `x += 1` | Declare (at the top, one per type) + Assign |
| `xs = [0] * n` (any value: `[0.0] * n`, `[""] * n`, `[False] * n`, `[1] * n`), `xs: list[int] = [0] * n` | Declare an array of size `n`, then a For loop that fills it (left out when the next loop stores into every element first) |
| `xs = [3, 1, 2]` | Declare an array of size 3 + Assign each element |
| `xs[i] = value`, `xs[i] = Input(int)` | Assign / Input into an element |
| `if ...: elif ...: else:` | If (an elif is an If in the False branch) |
| `while condition:` | While |
| `while True:` ... `if condition: break` (the break-if is the last statement) | Do, repeating while `not condition` |
| `for i in range(n)`, `range(a, b)`, `range(a, b, step)` | For from `a` (or 0) to `b - 1` for a positive step, or `b + 1` for a negative step; the step is a nonzero integer literal |
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
* Python fixes where `range()` ends when the loop starts, while Flowgorithm checks the end again
  every round, so the body must not change what the end is computed from (`for i in range(n)`
  with `n = n - 1` inside is reported; `Size(xs)` is fine, an array keeps its size).
* `Input(...)` names the type of the variable it reads into (`x = Input(float)` for a Real `x`),
  because Flowgorithm's Input reads whatever its variable holds.
* Arrays have a fixed size. A new Flowgorithm array holds no values (reading one stops the
  program, checked), so `[v] * n` becomes a Declare plus a loop that fills it. Arrays are not copied or
  returned, and are made once, outside loops (Flowgorithm declares them where they are made).
* There is no `//` (`Int(a / b)` truncates toward zero; it differs from Python's floor division
  for negative results), no f-strings (pass several values to `Output`), no
  `print`/`input`/`len`/`int`/`str` (use the library), no methods, slices, tuples, dictionaries,
  or general-purpose classes. Imports are limited to the library, sibling program files and
  `unittest` test code described above. Outside imports, function definitions, tests and the
  `main()` guard, top-level statements must define literal constants.

### What can still differ

The converter warns about these differences where it can. The
[probe results](docs/probe/README.md) record observations from Flowgorithm and the environment
used to check them:

* `%` with a negative number on either side: Flowgorithm stops the program ("Illegal Value: The
  value '-7' is not valid for the function % mod"), Python gives a result (`-7 % 2` is `1`,
  `7 % -2` is `-1`). Keep both sides of `%` at 0 or more (the converter rejects a negative number
  written out).
* `and` / `or`: Python skips the right side when the left side decides; Flowgorithm always
  evaluates both (checked). `while i < Size(xs) and xs[i] != x` is warned about: in Flowgorithm
  `xs[i]` runs even when `i < Size(xs)` is false and stops the program, so test it in a nested if
  (or use a found flag, as in [`examples/exercises/search.py`](../examples/exercises/search.py)).
* Ordering Strings with `<` / `>` (warned about): Python compares character codes (`"B" < "a"`).
  Flowgorithm under Wine did the same; on Windows it may order upper and lower case
  differently. `==` and `!=` are the same.
* Reals: the library shows at most 15 significant digits, as Flowgorithm does (`7 / 3` is
  `2.33333333333333`). But Flowgorithm also rounds every Real to 15 digits while calculating
  (checked), and Python's arithmetic does not: `0.1 + 0.2 == 0.3` is true there and false in
  Python, `1 / 3 * 3` shows `0.999999999999999` there and `1` in Python. `==` and `!=` between
  Reals are warned about: compare with a tolerance, like `Abs(a - b) < 0.000001`.
* Very large whole numbers: Flowgorithm's Integers are 64-bit and its arithmetic keeps 15
  significant digits (checked): `2147483648 * 2147483648` is `4611686018427389952` there and
  `4611686018427387904` in Python, and beyond 9223372036854775807 an Integer variable overflows.
  Keep whole numbers below 1 000 000 000 000 000.

## Checking the flowchart without Flowgorithm

The tools also run directly from the repository root, without installation:

```bash
python3 converter/src/fprg_lint.py program.fprg
python3 converter/src/fprg_run.py program.fprg --input 3
python3 converter/src/fprg2svg.py program.fprg -o program.svg
```

Only SVG rendering requires Graphviz's `dot` executable on `PATH`. Repeat `--input` for each
answer a program needs; `--random 3,5` supplies successive values for `Random()` calls.
Use your own `.fprg` path, such as `tickets.fprg` from the example above.
After optional installation, the shorter commands are:

* `fprg-lint file.fprg` (`fprg_lint.py`) — a strict validator for `.fprg` files (structure,
  identifiers, declared-before-use, Flowgorithm's expression grammar, light type checks).
* `fprg2svg file.fprg -o file.svg` (`fprg2svg.py`) — draws the flowchart with Graphviz.
* `fprg-run file.fprg --input 7 --random 3,5` (`fprg_run.py`) — a headless interpreter for
  `.fprg` files. The tests use it to run each program both ways: the Python program with the
  library and its flowchart must print exactly the same text.
* The browser viewer [FlowgorithmJS](https://andreaval.github.io/FlowgorithmJS/drawLocal.html)
  opens the generated files too; Flowgorithm itself (Windows, or the macOS port
  [jostasik/Flowgorithm-macOS](https://github.com/jostasik/Flowgorithm-macOS)) is the final proof.
* [`docs/probe/`](docs/probe/README.md) — four small flowcharts used to check run-time rules
  in Flowgorithm (how Reals are printed, `ToFixed` rounding, `%`,
  `and`/`or`, String order, the For counter, array start values, Integer size). Its README says
  what each output line means and records the results and test environment.

## Files

| Path | What |
|---|---|
| `src/py2fprg/` | the converter (`program.py` the file structure, `convert.py` statements and expressions, `layout.py` comments and `# fg:` directives, `model.py` the shapes, `writer.py` the XML, `cli.py`) |
| `src/fprg_lint.py`, `src/fprg2svg.py`, `src/fprg_run.py` | validator, renderer, interpreter for `.fprg` files |
| [`docs/fprg-format.md`](docs/fprg-format.md) | the reverse-engineered file format |
| `docs/probe/` | flowcharts that show Flowgorithm's undocumented run-time rules when run (`make_probe.py` builds them) |
| `tests/` | tests for the converter and the tools, and that the library agrees with `fprg_run` (`python3 -m unittest discover -s tests` in this folder) |
