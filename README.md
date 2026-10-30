# py2fprg — write Python, get Flowgorithm flowcharts

[Flowgorithm](http://www.flowgorithm.org) is a teaching tool in which programs are
*drawn* as flowcharts, shape by shape. Its `.fprg` files are plain XML that holds
exactly the structure of a program (functions, declarations, assignments, I/O,
if/while/for/do loops, calls), so a flowchart is really an AST with a picture.

`py2fprg` lets you write that program as ordinary Python — in several files, with
type annotations and unit tests — and generates the `.fprg` file from it:

```
your_project/                      python3 -m py2fprg your_project/
├── quiz.py        (main())   ───►   quiz.fprg   ◄── open in Flowgorithm
├── questions.py   (functions)        (Main + every function main() reaches,
├── prompts.py     (functions)         gathered from all modules)
└── tests/         (unit tests, never converted)
```

Everything is standard-library Python 3.11+; no installation needed.

## Quick start

```bash
# convert the sample project
python3 -m py2fprg examples/arith_quiz
# -> wrote examples/arith_quiz/quiz.fprg (12 functions, 113 shapes)

# validate the result and render a preview (Graphviz `dot` needed for --svg)
python3 -m py2fprg examples/arith_quiz --lint --svg

# only check whether a project is convertible, write nothing
python3 -m py2fprg examples/arith_quiz --check

# single file, explicit output, Flowgorithm 4.x file version
python3 -m py2fprg prog.py -o out/prog.fprg --fileversion 4.2
```

Run the sample's own unit tests (they are plain Python and are *not* part of the flowchart):

```bash
cd examples/arith_quiz && python3 -m unittest discover -s tests -t . -v
```

Run the converter's tests:

```bash
python3 -m unittest discover -s tests -v
```

## How a project maps to a flowchart

| Python | Flowgorithm |
|---|---|
| the function that `if __name__ == "__main__":` calls (`main()`, `sys.exit(main())`, also one imported from another module), else `def main():`, else the module-level code | the `Main` function (an `if __name__` block that does more than one call becomes Main itself, and `main()` an ordinary function) |
| `def f(a: int, xs: list[float]) -> str:` in any module `main()` reaches (directly or through imports) | a function with typed parameters; the return type comes from the annotation or is inferred |
| `return expr` at the end of a function, or inside an `if` (the statements after the `if` move into its `else`) | assignment to the function's return variable (Flowgorithm returns a variable's value when the function ends; there is no early return) |
| `x = 5`, `x: float = 0`, `x += 1`, `a, b = b, a` | `Declare` (hoisted to the top of the function, grouped by type) + `Assign`; a variable that later gets a float is Real from the start |
| `name = input("Prompt")`, `n = int(input("Prompt"))`, `x = float(input())` | `Output "Prompt"` + `Input` into a String / Integer / Real variable |
| `input()` inside an expression: `total += int(input("n? "))`, `if input("Again? ") == "y":`, `while input() != "":` | `Output` + `Input` into a variable (`answer`) right before the statement; for a loop condition before the loop and again at the end of its body |
| `print(a, "text", end="")`, f-strings, `f"{x:.2f}"` | `Output a & "text"` with newline on/off; `ToFixed(x, 2)` |
| `if / elif / else` | nested `If` shapes |
| `while cond:` | `While` |
| `while True: ... if cond: break` (break last) | `Do` loop with the negated condition |
| `while True: if cond: break ...` (break first) | `While` with the negated condition |
| `while True: A; if cond: break; B` (break in the middle) | `A`, then `While not cond: B; A` (a priming read) |
| `break`, `continue` and `return` anywhere in a loop, `for/while ... else` | a flag in the loop condition (`not done`, `not returned`); what follows a `continue`/`break`/`return` moves into the branches that go on; a `for` with `break` or `return` becomes a `While` over a hidden counter; the code after a loop that may return runs under `If not returned`; `else` runs under `If not done` |
| `for i in range(a, b, step)` | `For` from `a` to `b - 1` (inclusive end, `dec` for negative literal steps); when the body changes `i`, `i` is read after the loop or `i` is also a float, the `For` counts with a hidden `iCounter` and sets `i = iCounter` at the top of each pass |
| `for x in xs`, `for ch in s`, `for i, x in enumerate(xs)` | `For` over an index variable plus `x = xs[i]` / `Char(s, i)` |
| `xs = [0] * n`, `xs: list[str] = [""] * n`, `xs = [3, 4]`, `xs[i]`, `len(xs)` | array `Declare` with a size (in place, since the size is a runtime value), element assignment, `Size(xs)` |
| `for ch in "abc"`, `for x in [1, 2, 3]` | the literal goes into a variable (`text`, `values`), set up once at the top |
| `xs.sort()` (also `reverse=True`), `xs.reverse()`, `xs.index(x)`, `xs.count(x)`, `ys = sorted(xs)` / `list(xs)` / `xs.copy()` / `xs[:]` | loops over the fixed-size array (a stable bubble sort; `index` gives -1 where Python raises) |
| `xs[-1]`, `xs[-i]` | `Size(xs) - 1`; a computed one counts from the end only when it is negative, as in Python |
| `f(x)` as a statement | `Call` |
| `# comments`, docstrings | `Comment` shapes (not the shebang, the coding line or tool pragmas such as `# noqa`); the module docstring becomes the program's *about* text and title |
| module-level `MAX_TRIES = 3` | copied as a declared+assigned local into every function that uses it (Flowgorithm has no globals) |
| `math.sqrt/sin/cos/tan/asin/acos/atan/log/log10/fabs/pow/exp`, `math.pi` | `Sqrt`, `Sin`, …, `Ln`, `Log10`, `Abs`, `^`, `pi` |
| `math.floor(x)`, `math.ceil(x)`, `round(x)` | `Int(x)` (which truncates) plus one correction before the statement; `round` goes half to even, as in Python |
| `random.randint(a, b)`, `random.randrange(n)` | `a + Random(b - a + 1)`, `Random(n)` |
| `abs`, `round(x, n)`, `str`, `int(s)`, `float(s)`, `ord`, `chr`, `len(s)`, `s[i]` | `Abs`, `ToReal(ToFixed(x, n))`, `ToString`, `ToInteger`, `ToReal`, `ToCode`, `ToChar`, `Len`, `Char(s, i)` |
| `"*" * n`, `s.upper()`, `s.lower()`, `s.strip()` / `lstrip` / `rstrip`, `s.isdigit()`, `s.isalpha()`, `s.isupper()`, `s.islower()`, `s.count("a")`, `s[a:b]`, `s[::-1]` | a small loop over `Char` / `ToCode` / `ToChar` into a variable before the statement (letters and digits as in ASCII; slice bounds clamped as in Python) |
| `**`, `//`, `%`, `and/or/not`, comparisons, `a < b < c`, string `+` | `^`, `Int(a / b)`, `%`, `and/or/not`, `==` …, `a < b and b < c`, `&`. Flowgorithm's `//` and `%` truncate toward zero, so where an operand may be negative (a subtraction, a negative literal, a variable that held one) the result gets Python's rounding-down correction before the statement; non-negative operands and `% ... == 0` tests stay plain |
| `if n:`, `while s:`, `if not xs:` (Python truthiness) | explicit tests: `n != 0`, `s != ""`, `Size(xs) == 0` |
| `count += x > 0`, `score + (a == b)`, `int(flag)` (a Boolean as 1/0) | `If x > 0: count = count + 1`; otherwise an `If` that sets a variable to 1 or 0 |
| `a if c else b` | an `If` that assigns the value (directly to the target in `x = a if c else b` and `return a if c else b`) |
| `min(a, b, c)`, `max(xs)`, `sum(xs)` | comparisons (or a loop over the list) into a variable before the statement |
| `x in (1, 2, 3)`, `x in xs`, `x in range(a, b)`, `ch in "aeiou"`, `not in` | `x == 1 or x == 2 or x == 3`, a search loop, `x >= a and x < b`, `ch == "a" or ch == "e" ...` (one character against a string literal) |
| `a and input() == "y"` (something that needs statements on the right of `and`/`or`) | a Boolean `test` filled by nested `If`s, so the right side runs only when Python runs it |
| `lo <= f() <= hi`, `random.randint(low(), 10)`, `tally[random.randint(1, 6)] += 1`, `[f()] * n` | the call runs once, into a variable before the statement, as in Python |
| float literals Python writes with an exponent: `1e-05`, `1.602176634e-19`, `6.02e23` | `0.00001`, `1.602176634 * 10 ^ -19`, `6.02 * 10.0 ^ 23` (Flowgorithm has no exponent notation) |
| `snake_case`, names that clash with Flowgorithm keywords (`len`, `string`, …), names differing only in case, non-ASCII names | renamed (`snakeCase`, `lenVal`, `n2`, `größe` → `grosse`, `счёт` → `schet`): Flowgorithm identifiers are ASCII, allow no underscore and are case-insensitive |
| a nested `for` that reuses an enclosing loop's variable (`for _ in ...:` twice) | the outer loop counts with a hidden counter (`vCounter`), so the inner one cannot disturb it |

Test files (`test_*.py`, `*_test.py`, `tests/` and `test/` directories, `conftest.py`) are never
read. Other `.py` files in the tree that use unsupported Python are skipped with a warning and only
become an error if the program imports them. Functions that are not reachable from `main()` are
left out unless you pass `--all-functions`.

### Marks

Type annotations are the main mark: parameters need them (`n: int`, `xs: list[float]`) unless
every call passes a literal (`show(1)`, `scale(2.5)`) or they have a literal default, and local
variables need them rarely: a variable, parameter or list that starts out with integers and later
gets a float is simply Real. An annotation is a declaration, though, as for mypy: an `int`
variable, parameter, `list[int]` or `-> int` function never takes a float (that is an error,
because Flowgorithm would silently cut off the fraction).

Names follow Python's scoping: a name assigned anywhere in a function is local to it (it may
shadow a module constant). Module-level names assigned once, to a literal, are constants and are
copied into the functions that use them; any other module-level variable cannot be read in a
function, because Flowgorithm has no globals.

Everything else is a comment directive:

| Directive | Effect |
|---|---|
| `# fg: ignore` on a `def` (on any of its lines up to the `:`, a decorator line, or the comment lines above it) | the function is not converted; it may use any Python (test helpers, debugging aids). Calling it from converted code is an error. |
| `# fg: ignore` above a statement or trailing one of its lines | the statement is left out of the flowchart; for `if`/`for`/`while` (directive on a header line) the whole statement, on an `elif` line only that branch, on an `else:` line the else branch. A directive that has no statement to apply to gets a warning. |
| `# fg: breakpoint` | inserts a Breakpoint shape (a Python `breakpoint()` call does the same, but would also start the debugger when you run the Python version) |
| `# fg: name Title`, `# fg: about ...`, `# fg: author ...` | program attributes (defaults: the docstring's first line, the docstring, the current user) |
| `# fg: comment text` | an explicit Comment shape (plain `#` comments become comments anyway; `--no-comments` drops them) |

### What is not supported (reported as an error with file and line)

Flowgorithm has no exceptions, classes, dictionaries, tuples, growing lists (`append`, `insert`,
`pop`, `remove`), list slices other than `xs[:]`, substring search (`in` on strings beyond one
character, `find`, `replace`, `split`, `join`, `startswith`), nested lists, generators, lambdas,
global variables, and no string escape sequences (quotes and tabs inside strings are emitted
through `ToChar(n)`). String and list methods other than the ones in the table above are reported
as errors. Keep the interactive program inside that subset and put
everything else in `# fg: ignore` functions or in the tests.

### Where Python and Flowgorithm differ anyway

* Output: Flowgorithm prints a whole-number Real without the `.0` (`2`, where Python prints `2.0`)
  and Booleans as `true`/`false`.
* `input().strip()` is read with a plain `Input` (the usual defensive `.strip()` would otherwise
  turn every prompt into a loop); Flowgorithm keeps spaces the user types around the answer.
* `//` and `%` of values whose sign the converter cannot know (an input, a parameter) stay plain,
  so they truncate toward zero where Python rounds down; the converter warns.
* A literal written as `mantissa * 10 ^ exponent` may differ from Python's value in the last digit.
* When part of a statement has to run before it (an `input()` inside an expression, say), the calls
  that Python makes earlier in that statement go into variables as well, so the flowchart keeps
  Python's order of input, output and random numbers.

## Validating the output without Flowgorithm

* `fprg_lint.py file.fprg` — a strict validator for `.fprg` files: structure, identifier
  rules, declared-before-use, a full parser for Flowgorithm's expression grammar with
  arity checks, plus light type checks. It reports zero errors on 24 real files saved by
  Flowgorithm 1.0 through 4.2 (see `docs/fprg-format.md` for where they came from).
  `python3 -m py2fprg PATH --lint` runs it on what was generated; the converter's test
  suite lints every document it produces.
* `fprg2svg.py file.fprg -o file.svg` — draws the flowchart with Graphviz (`dot`) so you can
  look at it without Flowgorithm: Flowgorithm-style shapes, False left / True right, loop-backs,
  one cluster per function. `--function NAME` renders one function, `-o file.png|pdf|dot` picks
  the format, `--list-functions` lists them. `--svg` on the converter does the same for its output.
* `fprg_run.py file.fprg --input 7 --input yes --random 3,5` — a headless interpreter for
  `.fprg` files (every statement type, functions, arrays, intrinsics, Flowgorithm precedence).
  Scripted input lines and a fixed `Random()` sequence make runs reproducible. The test suite uses
  it for **differential testing**: each example program is run in Python with scripted `input()`
  and a patched `random.randint`, the generated flowchart is run by `fprg_run` with the same
  inputs, and the console transcripts must be identical. (Number formatting follows Flowgorithm's
  conventions as far as they are known; see the module docstring.)
* The third-party browser viewer [FlowgorithmJS](https://andreaval.github.io/FlowgorithmJS/drawLocal.html)
  also opens the generated files (it does not draw Comment shapes).
* Flowgorithm itself: Windows installer from flowgorithm.org; on macOS the community port
  [jostasik/Flowgorithm-macOS](https://github.com/jostasik/Flowgorithm-macOS) (v4.5,
  `brew tap jostasik/homebrew-tap && brew install --no-quarantine jostasik-flowgorithm`).
  Opening the generated file there is the final proof; everything above is a stand-in.

## The examples

`examples/guess_number.py` is a single-file program (the classic guessing game: a Do loop,
`elif`, a helper function, a module constant). `python3 -m py2fprg examples/guess_number.py`
writes `guess_number.fprg` next to it.

## The sample project

`examples/arith_quiz/` is the intended workflow in miniature:

* `quiz.py` — the interactive program (`main()`, `play_round`, `show_summary`), a
  `# fg: ignore` test helper, the `if __name__ == "__main__":` guard.
* `questions.py` — pure functions (question text, answers, percentage, grade, plural) and
  the shared constants.
* `prompts.py` — input helpers (`ask_int` with range validation, `ask_yes_no` as a Do loop).
* `tests/` — unit tests for the pure functions and the prompts (with mocked `input`), and an
  end-to-end test that runs `main()` with scripted answers and a fixed random sequence.

`python3 -m py2fprg examples/arith_quiz` produces `quiz.fprg` with Main plus 11 functions
gathered from the three modules; the tests and the ignored helper are not in it.

## Files

| Path | What |
|---|---|
| `py2fprg/` | the converter package (`model.py` types & shapes, `layout.py` comments, directives and the `# fg: ignore` pre-pass, `convert.py` statements/expressions, `project.py` modules/imports/call graph, `writer.py` XML, `cli.py`) |
| `fprg_lint.py` | `.fprg` validator |
| `fprg2svg.py` | Graphviz renderer |
| `fprg_run.py` | headless `.fprg` interpreter (used for differential tests) |
| `docs/fprg-format.md` | the reverse-engineered file-format reference |
| `examples/arith_quiz/` | sample project |
| `tests/` | tests for the converter, the linter, the renderer and the interpreter (incl. differential tests) |

## Known issues

`docs/bug-hunt-findings.md` lists the results of an adversarial multi-agent bug hunt: confirmed
semantic defects with repros and their status, rejected reports, and the triaged leads. All
confirmed findings are fixed or give a clean error, each with a regression test, except the
`//`/`%` of values with unknown signs, which keep Flowgorithm's truncation (with a warning).

## Notes on the file format

The format is not documented by Flowgorithm's author; `docs/fprg-format.md` was derived
from real files (fileversion 1.0, 1.7, 2.6, 2.11, 3.0, 4.2), the FlowgorithmJS parser and the
official language documentation. The statement set has been stable since version 2;
files written by Flowgorithm 4.x only differ in the `fileversion` attribute, so py2fprg
writes `3.0` by default (readable by 3.x and 4.x) and `--fileversion 4.2` is available.

Prior art: [flowo](https://pypi.org/project/flowo/) (a Python DSL that writes `.fprg`, i.e.
you call `flow.declare(...)`/`flow.if_(...)` instead of writing Python) and
[fgscript](https://github.com/mandriota/fgscript) (a macro language for the format).
py2fprg differs in taking real, runnable, testable Python as the source.
