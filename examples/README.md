# Flowgorithm exercises in Python

Programs written in Python the Flowgorithm way, with the
[`flowgorithm` library](../library), each next to the flowchart the [converter](../converter)
makes of it (`.fprg`, opens in Flowgorithm). Copy this folder to start your own project.

* `arith_quiz/` — an arithmetic quiz with input validation, arrays, Random and eleven small
  functions, with its own unit tests (`test_quiz.py`): how a program is tested.
* `exercises/` — sixteen classic first exercises, each a short program: `guess_number` (the
  classic guessing game: a Do loop, `elif`, a function, a constant), `fizzbuzz` (`%`,
  `elif`), `primes` (a Boolean function, a While with two conditions), `bubble` (an array, nested
  For loops, a swap), `palindrome` (`Char`, `Len`, a For counting down), `binary` (building a
  String, `Int(n / 2)`), `search` (a While with a found flag instead of `break`, the largest
  value, `ToFixed`), `table` (nested loops, `newline=False`, a For with a step), `gcd` (a loop and
  recursion), `vowels` (a function returning a condition), `grades` (`elif` chains, a loop that
  stops at -1), `caesar` (`ToCode`/`ToChar` arithmetic), `words` (taking a String apart), `stats`
  (an array sized by the input, an array parameter, a checked input in a Do loop), `menu` (a menu
  in a Do loop, functions without a result), `fib` (a running sequence, and recursion).
* `lab1_cinema/` — the start of a lab: Lab 1 Cinema Seats with task 1.1 done, in the layout the
  lab keeps to the end (`main.py` the program, a file for each task with its tests inside, a
  `.vscode` folder for VS Code). Copy that folder alone to start the lab; its README says how it
  goes on.
* `tests/test_examples.py` — plays every program in Python and as its flowchart.

## Your own project

The library and the converter are installed once, from the flowgorithm repository
(`python3 install.py` there; see its README). Then:

```bash
cp -r examples ~/my-flowgorithm      # in the flowgorithm repository
cd ~/my-flowgorithm
git init
```

Write a program like the ones here (the dialect is described in the
[converter's README](../converter/README.md)), and work with it:

```bash
python3 exercises/fizzbuzz.py              # run it
py2fprg exercises/fizzbuzz.py              # make its flowchart (py2fprg exercises: the whole folder)
python3 -m unittest discover -s tests      # play every program in Python and as a flowchart
```

On Windows, type `py` for `python3`, and `py -m py2fprg` for `py2fprg` (it works even when the
command's folder is not on PATH).

Every program gets its runs in the `RUNS` table of `tests/test_examples.py`: the answers it is
given, the values `Random()` returns, and texts the console must show. The test then requires
that the Python program and its flowchart print exactly the same, and that each saved `.fprg` is
what the converter makes of the program today (run `py2fprg` again after a change). Unit tests of
a program's functions go next to it, as in `arith_quiz/test_quiz.py`.
