# Sample project: Arithmetic Quiz

The workflow py2fprg is built for, in miniature: an interactive program written as
ordinary Python in several files, unit-tested in Python, converted to one Flowgorithm file.

```
quiz.py        main() and the game loop; a `# fg: ignore` helper used only by tests
questions.py   pure functions (question text, correct answer, percentage, grade, plural) + constants
prompts.py     ask_int (range-validated input) and ask_yes_no (a Do loop), is_yes / is_yes_or_no
tests/         unit tests (mocked input, scripted end-to-end run) — never converted
quiz.fprg      generated: Main + 11 functions from the three modules
```

```bash
python3 quiz.py                                   # play it in the terminal
python3 -m unittest discover -s tests -t . -v     # run the tests (from this directory)
cd ../.. && python3 -m py2fprg examples/arith_quiz --lint --svg   # regenerate quiz.fprg (+ preview)
```

Things to notice in the Python source:

* Only `input()` / `print()` for I/O, `int(input(...))` for numbers, no string methods.
* Early `return`s only inside `if` chains (they become if/else in the flowchart); no `return` in loops.
* `while True: ... if cond: break` with the break last is the Do-loop idiom.
* Arrays are created with `[False] * count`; lists never grow.
* Constants (`MAX_QUESTIONS`, `ADD`, ...) are module-level literals; the converter copies them
  into every function that uses them because Flowgorithm has no globals.
