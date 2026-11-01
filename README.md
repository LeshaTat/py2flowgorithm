# Converter from Python to Flowgorithm

[Flowgorithm](http://www.flowgorithm.org) programs are drawn as flowcharts, shape by shape. Here a
student writes the program in Python instead — in a small dialect that matches Flowgorithm one to
one — runs and tests it like any Python program, and gets the flowchart from it.

* **Who it is for:** students who already know how to code and have no trouble editing code in
  text files. The purpose is to make some use of Flowgorithm for them.
* **The conversion is one-way:** from Python to the flowchart. Nothing turns a `.fprg` back into
  Python, so a change made in Flowgorithm never reaches the program, and converting again
  overwrites it: change the Python and convert again.
* **Written by AI:** the library, the converter and the examples were written by Claude Opus 5.5,
  an AI model made by Anthropic.

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

1. Clone this repository and install the library and the converter for your Python (see
   [install.py](#installpy)):

   ```bash
   git clone https://github.com/LeshaTat/py2flowgorithm.git
   cd py2flowgorithm
   python3 install.py
   ```

2. Start your own project from the examples, in a repository of its own:

   ```bash
   cp -r examples ~/my-flowgorithm
   cd ~/my-flowgorithm
   git init
   python3 exercises/fizzbuzz.py            # run a program
   py2fprg exercises                        # make the flowcharts of a folder
   python3 -m unittest discover -s tests    # each program and its .fprg must print the same
   ```

   The test runs each program in Python and its `.fprg` in `fprg_run`, the converter's
   interpreter of `.fprg` files (not Flowgorithm), on the same typed answers.

   [`examples/README.md`](examples/README.md) explains the folder and how to add programs. A lab
   starts from one folder of it instead: `cp -r examples/lab1_cinema ~/lab1-cinema` (see
   [its README](examples/lab1_cinema/README.md)).

On Windows, where Flowgorithm runs, the same steps in PowerShell (`py -m py2fprg` works whether
or not the launchers' folder is on PATH):

```powershell
py install.py                                   # in the repository folder
Copy-Item -Recurse examples $HOME\my-flowgorithm
cd $HOME\my-flowgorithm
git init
py exercises\fizzbuzz.py
py -m py2fprg exercises
py -m unittest discover -s tests
```

## install.py

`python3 install.py` installs the library and the converter for the Python that runs it: that
Python's programs can then `from flowgorithm import *`, and `py2fprg` works in any folder.

If the shell says `py2fprg: command not found` try `python3 -m py2fprg`.
Uninstall: `python3 install.py --uninstall`.

## VS Code

The cinema example, [`examples/lab1_cinema`](examples/lab1_cinema/), comes with a `.vscode`
folder that sets VS Code up for the project. Copied into another project whose program is
`main.py`, it works there the same. It needs VS Code's Python extension.

First pick the Python that `install.py` was run with: Python: Select Interpreter in the Command
Palette (Ctrl+Shift+P, Cmd+Shift+P on a Mac).

To convert, open Run and Debug, choose Convert to Flowgorithm and press the green arrow (or F5,
or Run > Start Debugging): it writes the flowchart of every program in the folder, here
`main.fprg`. Terminal > Run Build Task (Ctrl+Shift+B, Cmd+Shift+B on a Mac) converts too and
lists the converter's errors in Problems, each with a link to its line.

To run the program, choose Play main.py in Run and Debug the same way.

The unit tests are in the Testing view: VS Code finds the tests in every `.py` file of the
project and runs one test, one file's or all of them from there.

## Tests

`python3 run_tests.py` runs the tests of all three projects with this folder's code. They include
the check that matters most: every example and test program is converted with py2fprg, its
`.fprg` is run in `fprg_run` (the converter's interpreter of `.fprg` files, not Flowgorithm), and
it must print exactly what the Python program prints.
