# Lab 1: Cinema Seats, the start

Lab 1 (Grade 9, Flowgorithm arrays) with its first task done, laid out the way the lab goes on to
the end. Task 1.1 asks nothing, so the program is already the menu of task 1.7, with a made-up
option for now: Show seats, which shows task 1.1's map. Copy this folder to start the lab.

| File | What it is |
|---|---|
| `main.py` | the program: books seats 2, 5 and 7, then does what the menu's choice says until Quit; its tests play it with typed answers |
| `menu.py` | the menu (1 Show seats, 2 Quit) and `read_number`, which asks until a number is in range, with their tests |
| `task_1_1.py` | task 1.1, the seats and the seat map: `book`, `seat_map`, `show_map`, with their tests |
| `main.fprg` | the flowchart of main.py, with every function it uses |
| `.vscode/` | VS Code: the tests in the Testing view, buttons to play the program and to convert it |

No installation is required: copy `library/src/flowgorithm.py` from the
[py2flowgorithm](https://github.com/LeshaTat/py2flowgorithm) repository into the lab folder and
convert with `python3 /path/to/py2flowgorithm/py2fprg.py main.py`.
The commands and VS Code setup below assume the optional `python3 install.py` convenience
setup, which makes the library and converter commands available from any folder for your Python.

```bash
cp -r examples/lab1_cinema ~/lab1-cinema       # in the py2flowgorithm repository
cd ~/lab1-cinema
git init
python3 main.py                                # play it
python3 -m unittest discover -p "*.py" -v      # every file's tests
py2fprg main.py                                # make main.fprg again after a change
```

On Windows, type `py` for `python3` and `py -m py2fprg` for `py2fprg`.

## The next tasks

Each task gets a file of its own (`task_1_2.py`, `task_1_3.py`, ...) with its functions and a
`unittest.TestCase` class that tests them. A file imports what it uses from the others
(`from task_1_2 import book_seat`), as long as the imports don't go in a circle. py2fprg follows
the imports, so main.fprg holds every function the program uses; the test classes and
`import unittest` stay out of the flowchart.

## VS Code

Pick the Python that install.py was run with (Python: Select Interpreter). The Testing view then
runs every file's tests. Run and Debug has Play main.py and Convert to Flowgorithm, and
Terminal > Run Build Task (Ctrl+Shift+B, Cmd+Shift+B on a Mac) converts too, with the
converter's errors in Problems. The `.vscode` folder works the same in any project whose program
is `main.py`.
