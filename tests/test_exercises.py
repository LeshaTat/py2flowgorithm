"""The exercises in examples/exercises (run: python3 -m unittest tests.test_exercises -v).

Each exercise is run in Python (with the flowgorithm library) and as its flowchart (with
fprg_run) on the same answers: the console text must be identical. The .fprg files next to the
exercises must be what the converter makes of them today.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fprg_lint  # noqa: E402
import fprg_run  # noqa: E402
from py2fprg import convert_file  # noqa: E402
from test_py2fprg import run_python  # noqa: E402

FOLDER = os.path.join(ROOT, "examples", "exercises")

# the answers each exercise is played with
RUNS = {
    "binary": [["0"], ["10"], ["255"]],
    "bubble": [["5", "3", "9", "-1", "3"]],
    "caesar": [["Hello, World!", "3"], ["xyz", "25"], ["", "5"]],
    "fib": [["10"], ["0"], ["1"]],
    "fizzbuzz": [["15"], ["0"]],
    "gcd": [["12", "18"], ["7", "0"], ["0", "5"]],
    "grades": [["95", "85", "72", "61", "10", "-1"], ["-1"]],
    "menu": [["1", "2", "3", "2", "2.5", "4", "3", "2", "10", "9", "0"], ["0"]],
    "palindrome": [["level"], ["abc"], [""], ["a"]],
    "primes": [["30"], ["2"], ["1"]],
    "search": [["15"], ["7"], ["42"]],
    "stats": [["0", "101", "4", "1.5", "-2", "10", "3"], ["1", "7"]],
    "table": [["3"]],
    "vowels": [["hello world"], [""]],
    "words": [["the quick brown fox"], ["  spaced   out  "], [""], ["one"]],
}


def without_attributes(xml: str) -> str:
    """The document without its <attribute> lines (author, dates)."""
    return re.sub(r"\s*<attribute [^>]*/>", "", xml)


class ExercisesTest(unittest.TestCase):
    def test_every_exercise_is_played(self):
        names = sorted(f[:-3] for f in os.listdir(FOLDER) if f.endswith(".py"))
        self.assertEqual(names, sorted(RUNS))

    def test_python_and_flowchart_print_the_same(self):
        for name, runs in RUNS.items():
            path = os.path.join(FOLDER, name + ".py")
            with open(path, encoding="utf-8") as fh:
                code = fh.read()
            xml = convert_file(path, metadata=False)
            self.assertEqual([f for f in fprg_lint.lint_string(xml, name) if f.severity == "ERROR"], [])
            for inputs in runs:
                with self.subTest(exercise=name, inputs=inputs):
                    self.assertEqual(run_python(code, inputs), fprg_run.run_string(xml, list(inputs)))

    def test_the_flowcharts_are_up_to_date(self):
        for name in RUNS:
            with self.subTest(exercise=name):
                with open(os.path.join(FOLDER, name + ".fprg"), encoding="utf-8") as fh:
                    saved = fh.read()
                made = convert_file(os.path.join(FOLDER, name + ".py"))
                self.assertEqual(without_attributes(saved), without_attributes(made),
                                 f"regenerate it: python3 -m py2fprg examples/exercises/{name}.py")


if __name__ == "__main__":
    unittest.main()
