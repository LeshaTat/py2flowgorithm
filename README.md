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
python3 sum.py      # run it: it behaves the way the flowchart will
py2fprg sum.py      # -> sum.fprg, open it in Flowgorithm
```

This repository holds three projects:

| Folder | What it is |
|---|---|
| [`library/`](library/) | `flowgorithm`: Flowgorithm's `Output`, `Input` and built-in functions, with Flowgorithm's behaviour — every program imports it |
| [`converter/`](converter/) | `py2fprg`: turns such a program into a `.fprg` flowchart and defines the dialect; tools to check, draw and run `.fprg` files |
| [`examples/`](examples/) | a starting point for your own work: example programs with their flowcharts and tests |

## Getting started

You need Python 3.11 or newer; nothing outside the standard library.

1. Clone this repository and install the library and the converter for your Python:

   ```bash
   git clone <this repository> flowgorithm
   cd flowgorithm
   python3 install.py
   ```

   Now every program run with that Python can `from flowgorithm import *`, and `py2fprg` works in
   any folder. Nothing is copied: Python reads both projects from the clone, so `git pull` updates
   them. `python3 install.py --uninstall` takes it out again; run `install.py` again after moving
   the clone, and once for every other Python you use (IDLE, an IDE, another version).

2. Start your own project from the examples, in a repository of its own:

   ```bash
   cp -r examples ~/my-flowgorithm
   cd ~/my-flowgorithm
   git init
   python3 exercises/fizzbuzz.py            # run a program
   py2fprg exercises                        # make the flowcharts of a folder
   python3 -m unittest discover -s tests    # play every program in Python and as a flowchart
   ```

   [`examples/README.md`](examples/README.md) explains the folder and how to add programs.

With pip instead: in a virtual environment, `pip install -e library -e converter` does the same
for that environment.

## Tests

`python3 run_tests.py` runs the tests of all three projects against this clone. They include the
check that matters most: every example and test program, run in Python with the library and run
as its flowchart (with the converter's interpreter, `fprg_run`), prints exactly the same text.

The projects depend on each other in one direction: the library stands alone; the converter knows
the library's functions and runs programs with it in its tests; the examples need both. A change
that touches more than one of them goes in one commit.
