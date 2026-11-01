# Arithmetic Quiz

A complete Flowgorithm exercise solved in Python with the `flowgorithm` library:

* `quiz.py` — the program (input validation, a Do loop for yes/no answers, an array of results,
  `Random`, eleven small functions and `main()`).
* `test_quiz.py` — its unit tests: the functions on their own, and whole games played with
  scripted answers (`builtins.input`) and dice (`random.randrange`).
* `quiz.fprg` — the flowchart, made with `py2fprg quiz.py`.

Run the program and the tests from this folder (with the library installed, `python3 quiz.py`
is enough):

```bash
PYTHONPATH=../../library python3 quiz.py
python3 -m unittest -v
```
