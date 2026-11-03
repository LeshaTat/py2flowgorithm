# Flowgorithm exercises in Python

These programs use the [`flowgorithm` library](../library/README.md). Each program is stored
beside its generated `.fprg` flowchart, which opens in Flowgorithm. Copy an example to start
your own project, or use it to learn the [supported Python dialect](../converter/README.md#the-dialect).

The examples were written with Claude Opus 5.5 (Anthropic) and GPT-6 Astra (OpenAI), like the
library and converter.

## Examples

| Folder or file | What it demonstrates |
|---|---|
| [`exercises/`](exercises/) | Sixteen short exercises covering loops, strings, arrays, functions and recursion |
| [`arith_quiz/`](arith_quiz/README.md) | An arithmetic quiz with input validation, random questions, arrays and separate unit tests |
| [`lab1_cinema/`](lab1_cinema/README.md) | A program split across files, tests beside the functions, and VS Code run/test configurations |
| [`tests/test_examples.py`](tests/test_examples.py) | Checks that each Python program and its flowchart print the same output and that saved flowcharts are up to date |

The short exercises are:

| Program | Topics |
|---|---|
| [`guess_number.py`](exercises/guess_number.py) | Random numbers, a Do loop and branches |
| [`fizzbuzz.py`](exercises/fizzbuzz.py) | Remainders and conditions |
| [`primes.py`](exercises/primes.py) | Boolean functions and nested loops |
| [`bubble.py`](exercises/bubble.py) | Array sorting and swapping elements |
| [`palindrome.py`](exercises/palindrome.py) | String indexing and a loop that counts down |
| [`binary.py`](exercises/binary.py) | Building a string and integer conversion |
| [`search.py`](exercises/search.py) | Array search with a found flag |
| [`table.py`](exercises/table.py) | Nested loops, step sizes and formatted output |
| [`gcd.py`](exercises/gcd.py) | Loops and recursion |
| [`grades.py`](exercises/grades.py) | Branches and sentinel input |
| [`caesar.py`](exercises/caesar.py) | Character codes and string conversion |
| [`stats.py`](exercises/stats.py) | Arrays sized by input and array parameters |
| [`vowels.py`](exercises/vowels.py) | Character tests and counting |
| [`words.py`](exercises/words.py) | Finding word boundaries in a string |
| [`menu.py`](exercises/menu.py) | A repeating menu and functions |
| [`fib.py`](exercises/fib.py) | Iteration and recursion |

## Your own project

No installation is needed. From the repository root, copy the examples and put the library
beside the exercise programs:

```bash
cp -r examples ~/my-flowgorithm
cp library/src/flowgorithm.py ~/my-flowgorithm/exercises/
python3 ~/my-flowgorithm/exercises/fizzbuzz.py
python3 py2fprg.py ~/my-flowgorithm/exercises/fizzbuzz.py
```

The last command writes `fizzbuzz.fprg` beside the copied program. To convert all the short
exercises, pass `~/my-flowgorithm/exercises/` instead of the file path. Folder conversion does
not descend into subfolders.

In Windows PowerShell, from the repository root:

```powershell
Copy-Item -Recurse examples $HOME\my-flowgorithm
Copy-Item library\src\flowgorithm.py $HOME\my-flowgorithm\exercises\
py $HOME\my-flowgorithm\exercises\fizzbuzz.py
py py2fprg.py $HOME\my-flowgorithm\exercises\fizzbuzz.py
```

If you use the quiz or cinema example, copy `flowgorithm.py` into that example's folder too;
see its README for commands. Use a new destination folder when copying an example project.
You can then run `git init` in the copied project to track your changes.

The optional [install.py setup](../README.md#installpy) makes the library and converter tools
available from any folder for your Python. With that setup, library copies are unnecessary,
and `py2fprg program.py` or `python3 -m py2fprg program.py` converts a program from its own
folder. Use `py` in place of `python3` on Windows.

## Tests and new programs

In the original checkout, run `python3 run_tests.py` from the repository root; it needs no
installation. To run only the example comparison tests from the root, use:

```bash
python3 -m unittest discover -s examples/tests -v
```

For a standalone copy of `examples/`, the comparison tests also need the library and
converter tools on Python's import path. The optional setup supplies them. From the copied
project root, run `python3 -m unittest discover -s tests -v`. The quiz and cinema READMEs show
how to run their own unit tests with just a local library copy.

When adding a program:

1. Give it a `main()` function and follow the dialect. Add unit tests for its functions.
2. Generate its `.fprg` file with the converter; keep the Python source and flowchart together.
3. Add its relative path to `RUNS` in `tests/test_examples.py`, with input answers, fixed random
   values where needed, and expected output fragments.
4. Run the comparison tests. They check that every program has a `RUNS` entry, that its Python
   and interpreted flowchart output agree, and that the saved `.fprg` matches a fresh conversion.

Regenerate the flowchart after changing a program. The comparison tests use this project's
`fprg_run` interpreter; open the flowchart in Flowgorithm to check it there as well.
