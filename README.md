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
  `def main():`; test files and `flowgorithm.py` are skipped). Several files and folders can be
  given at once; a program with an error is reported and the others are still converted.
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

What can still differ (Flowgorithm's run-time rules are not all documented, so the converter warns
where it can; the probe flowcharts in `docs/probe/` settle these with one run in Flowgorithm):

* `%` with a negative number: Python's `-7 % 2` is `1`, Flowgorithm's is `-1`.
* `and` / `or`: Python skips the right side when the left side decides; Flowgorithm may evaluate
  both. `while i < Size(xs) and xs[i] != x` is warned about: the index must also work when
  `i < Size(xs)` is false, so test it in a nested if (or use a found flag, as in
  `examples/exercises/search.py`).
* Ordering Strings with `<` / `>` (warned about): Python compares character codes (`"B" < "a"`),
  Flowgorithm may order upper and lower case differently. `==` and `!=` are the same.
* Reals that do not end, like `7 / 3`: the library prints all the digits Python has
  (`2.3333333333333335`), an older Flowgorithm may print fewer. Show such results with
  `ToFixed(x, 2)`. `ToFixed` of a value exactly halfway (`ToFixed(2.25, 1)`) may round the other
  way.
* Very large whole numbers: Python's Integers have no limit, Flowgorithm's have a fixed size
  (keep them below 2 147 483 647, or use a Real).

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
* `docs/probe/` — four small flowcharts that show, run once in real Flowgorithm, the run-time
  rules the library and `fprg_run.py` had to guess (how Reals are printed, `ToFixed` rounding,
  `%`, `and`/`or`, String order, the For counter, array start values, Integer size). Its README
  says what each output line means.

## The examples

* `examples/guess_number.py` — the classic guessing game: a Do loop, `elif`, a function, a constant.
* `examples/arith_quiz/quiz.py` — an arithmetic quiz with input validation, arrays, Random and
  several functions, and its tests in `examples/arith_quiz/test_quiz.py`
  (`cd examples/arith_quiz && python3 -m unittest -v`).
* `examples/exercises/` — fifteen classic first exercises, each a short program: `fizzbuzz`
  (`%`, `elif`), `primes` (a Boolean function, a While with two conditions), `bubble` (an array,
  nested For loops, a swap), `palindrome` (`Char`, `Len`, a For counting down), `binary`
  (building a String, `Int(n / 2)`), `search` (a While with a found flag instead of `break`,
  the largest value, `ToFixed`), `table` (nested loops, `newline=False`, a For with a step), `gcd`
  (a loop and recursion), `vowels` (a function returning a condition), `grades` (`elif` chains,
  a loop that stops at -1), `caesar` (`ToCode`/`ToChar` arithmetic), `words` (taking a String
  apart), `stats` (an array sized by the input, an array parameter, a checked input in a Do
  loop), `menu` (a menu in a Do loop, functions without a result), `fib` (a running sequence, and recursion).
  `tests/test_exercises.py` plays each one in Python and as a flowchart and checks that both
  print the same.

The `.fprg` files next to them are the converter's output.

## Files

| Path | What |
|---|---|
| `flowgorithm.py` | the library student programs import |
| `py2fprg/` | the converter (`program.py` the file structure, `convert.py` statements and expressions, `layout.py` comments and `# fg:` directives, `model.py` the shapes, `writer.py` the XML, `cli.py`) |
| `fprg_lint.py`, `fprg2svg.py`, `fprg_run.py` | validator, renderer, interpreter for `.fprg` files |
| `docs/fprg-format.md` | the reverse-engineered file format |
| `docs/probe/` | flowcharts that show Flowgorithm's undocumented run-time rules when run (`make_probe.py` builds them) |
| `examples/` | example programs with their flowcharts |
| `tests/` | tests for the library, the converter and the tools (`python3 -m unittest discover -s tests`) |
