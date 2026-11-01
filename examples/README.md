# Examples

Programs written in Python the Flowgorithm way, with the [`flowgorithm` library](../library), each
next to the flowchart the [converter](../converter) makes of it (`.fprg`, opens in Flowgorithm).

* `guess_number.py` — the classic guessing game: a Do loop, `elif`, a function, a constant.
* `arith_quiz/` — an arithmetic quiz with input validation, arrays, Random and eleven small
  functions, with its own unit tests (`test_quiz.py`): how a program is tested.
* `exercises/` — fifteen classic first exercises, each a short program: `fizzbuzz` (`%`,
  `elif`), `primes` (a Boolean function, a While with two conditions), `bubble` (an array, nested
  For loops, a swap), `palindrome` (`Char`, `Len`, a For counting down), `binary` (building a
  String, `Int(n / 2)`), `search` (a While with a found flag instead of `break`, the largest
  value, `ToFixed`), `table` (nested loops, `newline=False`, a For with a step), `gcd` (a loop and
  recursion), `vowels` (a function returning a condition), `grades` (`elif` chains, a loop that
  stops at -1), `caesar` (`ToCode`/`ToChar` arithmetic), `words` (taking a String apart), `stats`
  (an array sized by the input, an array parameter, a checked input in a Do loop), `menu` (a menu
  in a Do loop, functions without a result), `fib` (a running sequence, and recursion).

## Running them

With the library and the converter installed (see the [repository's README](../README.md)):

```bash
python examples/exercises/fizzbuzz.py      # run a program
py2fprg examples/exercises                 # make the flowcharts of a whole folder
```

Without installing anything, from the repository root:

```bash
PYTHONPATH=library python3 examples/exercises/fizzbuzz.py
PYTHONPATH=converter python3 -m py2fprg examples/exercises
```

## Tests

`tests/test_examples.py` plays every program in Python and as its flowchart (with the converter's
interpreter) on the same answers and Random() values: the console text must be identical, and
each saved `.fprg` must be what the converter makes today. A new program gets its runs in the
`RUNS` table there. From the repository root:

```bash
python3 -m unittest discover -s examples/tests
python3 -m unittest discover -s examples/arith_quiz
```
