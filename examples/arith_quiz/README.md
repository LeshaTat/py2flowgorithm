# Arithmetic Quiz

A complete example using the `flowgorithm` library. The player chooses how many questions to
answer, solves random arithmetic problems and receives a grade. The program demonstrates
input validation, arrays, functions and repeatable tests for random behaviour.

| File | Contents |
|---|---|
| [`quiz.py`](quiz.py) | The program: input validation, random questions, scores and results |
| [`test_quiz.py`](test_quiz.py) | Unit tests for functions and complete games with scripted input and random values |
| [`quiz.fprg`](quiz.fprg) | The generated flowchart; open it in Flowgorithm |

## Run and test

Use Python 3.11 or newer. From the repository root:

```bash
cp library/src/flowgorithm.py examples/arith_quiz/
cd examples/arith_quiz
python3 quiz.py
python3 -m unittest -v
```

Installation is optional. If you have already run `install.py` with this Python, skip the
library copy. In PowerShell, use `Copy-Item` for `cp` and `py` for `python3`.

To regenerate the flowchart, run this from `examples/arith_quiz/`:

```bash
python3 ../../py2fprg.py quiz.py --lint
```

If you copy the quiz folder elsewhere, put `flowgorithm.py` beside `quiz.py` and replace
`../../py2fprg.py` with the full path to the checkout's launcher. After optional installation,
`python3 -m py2fprg quiz.py --lint` works too.

The tests replace typed answers and random values, so each game is repeatable. To also compare
Python output with the generated flowchart, run `python3 run_tests.py` from the repository
root; see the [example test guide](../README.md#tests-and-new-programs).
