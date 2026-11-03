# Lab 1: Cinema Seats, the start

This starter project implements task 1.1 of the Grade 9 lab on Flowgorithm arrays: storing
seat bookings and displaying a seat map. A small menu lets you show the map or quit, ready for
later tasks to add more options. Copy this folder to start the lab.

| File | What it is |
|---|---|
| `main.py` | the program: books seats 2, 5 and 7, then does what the menu's choice says until Quit; its tests play it with typed answers |
| `menu.py` | the menu (1 Show seats, 2 Quit) and `read_number`, which asks until a number is in range, with their tests |
| `task_1_1.py` | task 1.1, the seats and the seat map: `book`, `seat_map`, `show_map`, with their tests |
| `main.fprg` | the flowchart of main.py, with every function it uses |
| `.vscode/` | VS Code: the tests in the Testing view, buttons to play the program and to convert it |

## Run and test

Use Python 3.11 or newer. From the repository root, copy the lab to a new folder and put the
library beside its programs:

```bash
cp -r examples/lab1_cinema ~/lab1-cinema
cp library/src/flowgorithm.py ~/lab1-cinema/
python3 py2fprg.py ~/lab1-cinema/main.py --lint
cd ~/lab1-cinema
python3 main.py
python3 -m unittest discover -p "*.py" -v
```

The menu accepts `1` to show the seats and `2` to quit. The map displays array indexes 0–9;
functions such as `book()` take seat numbers 1–10.

In Windows PowerShell, from the repository root:

```powershell
Copy-Item -Recurse examples\lab1_cinema $HOME\lab1-cinema
Copy-Item library\src\flowgorithm.py $HOME\lab1-cinema\
py py2fprg.py $HOME\lab1-cinema\main.py --lint
cd $HOME\lab1-cinema
py main.py
py -m unittest discover -p "*.py" -v
```

No installation is required. To regenerate `main.fprg` from inside your lab folder, use
`python3 /path/to/py2flowgorithm/py2fprg.py main.py --lint`. The optional
[install.py setup](../../README.md#installpy) removes the need to copy the library and lets you
use `python3 -m py2fprg main.py --lint` instead. Run `git init` in the lab folder if you want to
track your work in its own repository.

## The next tasks

Each task gets a file of its own (`task_1_2.py`, `task_1_3.py`, ...) with its functions and a
`unittest.TestCase` class that tests them. A file imports what it uses from the others
(`from task_1_2 import book_seat`), as long as the imports don't go in a circle. py2fprg follows
the imports, so main.fprg holds every function the program uses; the test classes and
`import unittest` stay out of the flowchart.

## VS Code

Open the lab folder in VS Code with the Python extension. The supplied configurations use
`python -m py2fprg`, so after optional installation, choose the same Python with
**Python: Select Interpreter**.

To use the checkout directly without installation, keep `flowgorithm.py` in the lab folder
and adjust the supplied configurations:

- In `.vscode/launch.json`, replace `"module": "py2fprg"` in **Convert to Flowgorithm** with
  `"program": "/path/to/py2flowgorithm/py2fprg.py"`.
- In `.vscode/tasks.json`, replace `"args": ["-m", "py2fprg", ".", "--lint"]` with
  `"args": ["/path/to/py2flowgorithm/py2fprg.py", ".", "--lint"]`.

Use the actual launcher path. On Windows, forward slashes such as `C:/code/py2flowgorithm/py2fprg.py`
work in these JSON strings.

The **Testing** view discovers tests in every `.py` file. **Run and Debug** offers
**Play main.py** and **Convert to Flowgorithm**. **Terminal > Run Build Task** also converts
(Ctrl+Shift+B, or Cmd+Shift+B on a Mac) and shows converter errors in **Problems**.
The `.vscode` folder can be reused in another project whose entry point is `main.py`.
