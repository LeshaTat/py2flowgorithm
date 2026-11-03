# Python to Flowgorithm

Write and test a program in Python, then convert it to a [Flowgorithm](http://www.flowgorithm.org)
flowchart (`.fprg`). This project is for students who prefer writing code and need a flowchart
of their program. It accepts a [small Python dialect](converter/README.md#the-dialect) that maps
to Flowgorithm's shapes.

Conversion is one-way. Edit the Python source and convert again; converting overwrites the
`.fprg` file, including changes made in Flowgorithm.

Installation is optional. Copy `library/src/flowgorithm.py` next to your Python program to run
it, and use the converter directly from this checkout to generate its flowchart. The optional
[install.py](#installpy) makes the library and converter commands available from any folder
for your chosen Python.

The library, converter and examples were written with Claude Opus 5.5 (Anthropic) and
GPT-6 Astra (OpenAI).

## Getting started

You need Python 3.11 or newer. Running the Python programs and generating `.fprg` files uses
only the standard library. Flowgorithm opens and runs the generated flowcharts; Graphviz is
needed only for optional SVG previews.

Clone the repository and enter its folder:

```bash
git clone https://github.com/LeshaTat/py2flowgorithm.git
cd py2flowgorithm
```

Save the example below as `sum.py` in that folder. Generate `sum.fprg` with:

```bash
python3 py2fprg.py sum.py
```

On Windows, use `py py2fprg.py sum.py`. Open `sum.fprg` in Flowgorithm.

```python
"""Sum of Numbers.

Adds up the numbers from 1 to n."""
from flowgorithm import Input, Output


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

To run the same program in Python, copy the library beside it:

```bash
cp library/src/flowgorithm.py .
python3 sum.py
```

In Windows PowerShell:

```powershell
Copy-Item library\src\flowgorithm.py .
py sum.py
```

Enter `5` when prompted; the program prints `The sum is 15`.

Your program can live anywhere. Copy `flowgorithm.py` beside it, then use the converter's
path to generate its flowchart:

```bash
python3 /path/to/py2flowgorithm/py2fprg.py /path/to/sum.py
```

Replace the example paths with your own; `sum.fprg` is written beside `sum.py`. Conversion
reads the Python source without running it, so it does not need the copied library file.

## Examples and reference

| Folder | Contents |
|---|---|
| [Library](library/README.md) | `Input`, `Output`, built-in functions and helpers for testing Python programs |
| [Converter](converter/README.md) | Supported Python syntax, conversion options, and tools to validate, draw and run `.fprg` files |
| [Examples](examples/README.md) | Programs with their generated flowcharts and tests; instructions for starting your own project |

Start with the [short exercises](examples/README.md#examples), the
[arithmetic quiz](examples/arith_quiz/README.md), or the
[cinema lab](examples/lab1_cinema/README.md). The converter reference also explains
[where Python and Flowgorithm can differ](converter/README.md#what-can-still-differ).

## install.py

Installation is only a convenience for working across project folders. Run this once from the
repository root with the Python you want to use:

```bash
python3 install.py
```

On Windows, use `py install.py`. Afterward, that Python can import the library without a local
copy of `flowgorithm.py`, and these commands work from your project folder:

```bash
python3 sum.py
python3 -m py2fprg sum.py
```

You can also use the shorter `py2fprg sum.py` if the launchers' folder is on `PATH`.
The installer prints that location. In PowerShell, use `py` in place of `python3`.

The installer references this checkout rather than copying its source files. Keep the checkout
in place; if you move it, run `install.py` again from its new location. Updates in this checkout
take effect directly. Setup applies to the selected Python environment, including an active
virtual environment, rather than every Python installation on the machine.

To remove the import paths and launchers it added, use the same Python:

```bash
python3 install.py --uninstall
```

## VS Code

The [cinema example](examples/lab1_cinema/README.md#vs-code) includes a `.vscode` folder with
run, conversion and test configurations for a project whose entry point is `main.py`.
Its README explains the setup with or without installation.

## Troubleshooting

| Problem | What to check |
|---|---|
| `No module named 'flowgorithm'` | Copy `library/src/flowgorithm.py` beside the program that imports it, or run `install.py` with the Python used to run that program. |
| `py2fprg: command not found` | Run `python3 /path/to/py2flowgorithm/py2fprg.py program.py` directly, or use `python3 -m py2fprg program.py` after optional installation. |
| `No module named 'py2fprg'` | Use the checkout launcher, or run `install.py` with the same Python interpreter. In VS Code, check **Python: Select Interpreter**. |
| SVG rendering cannot find `dot` | Graphviz's `dot` executable must be on `PATH`. Generating `.fprg` files does not need Graphviz. |
| Conversion reports unsupported Python | Follow the file and line in the error and consult the [dialect reference](converter/README.md#the-dialect). |

## Tests

Run all five test suites from the repository root; installation is not required:

```bash
python3 run_tests.py
```

The runner uses this checkout's library and converter. Tests compare example programs with
their generated flowcharts using `fprg_run`, check that saved example flowcharts are up to date,
and exercise the library and converter tools. `fprg_run` is this project's interpreter;
comparison with it does not replace checking a flowchart in Flowgorithm itself.

Nine tests in `SampleFilesTest` use external Flowgorithm sample files that are not included in
this repository. They skip when the sample folder is absent. If you have the matching files,
set `FPRG_SAMPLES` to their folder; the filenames are listed in
[`converter/tests/test_fprg_run.py`](converter/tests/test_fprg_run.py).
Graphviz rendering tests also skip when `dot` is unavailable.
