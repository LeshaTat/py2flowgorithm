# Flowgorithm in Python

[Flowgorithm](http://www.flowgorithm.org) programs are drawn as flowcharts, shape by shape. Here a
student writes the program in Python instead — in a small dialect that matches Flowgorithm one to
one — runs and tests it like any Python program, and gets the flowchart from it.

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
python sum.py                       # run it: it behaves the way the flowchart will
py2fprg sum.py                      # -> sum.fprg, open it in Flowgorithm
```

This repository holds three projects:

| Folder | What it is | Who uses it |
|---|---|---|
| [`library/`](library/) | `flowgorithm.py`: Flowgorithm's `Output`, `Input` and built-in functions, with Flowgorithm's behaviour | every program imports it |
| [`converter/`](converter/) | `py2fprg`: turns such a program into a `.fprg` flowchart, and defines the dialect; tools to check, draw and run `.fprg` files | students and teachers, one command per program or folder |
| [`examples/`](examples/) | programs written this way, with their flowcharts and tests | everyone: what the programs look like |

## Getting started

Python 3.11 or newer; nothing outside the standard library.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e library -e converter
python examples/exercises/fizzbuzz.py      # run a program
py2fprg examples/exercises/fizzbuzz.py     # make its flowchart
```

Without installing anything: copy `library/flowgorithm.py` next to the program, and run the
converter as `PYTHONPATH=converter python3 -m py2fprg program.py`.

## Tests

`python3 run_tests.py` runs the tests of all three projects. They include the check that matters
most: every example and test program, run in Python with the library and run as its flowchart
(with the converter's interpreter, `fprg_run`), prints exactly the same text.

The projects depend on each other in one direction: the library stands alone; the converter knows
the library's functions and runs programs with it in its tests; the examples need both. A change
that touches more than one of them goes in one commit.
