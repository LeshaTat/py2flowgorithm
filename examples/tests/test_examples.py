"""Every example program, played in Python and as its flowchart (run from the repository root:
python3 -m unittest discover -s examples/tests).

Each program runs in Python (with the flowgorithm library) and as its flowchart (with the
converter's interpreter, fprg_run) on the same answers and Random() values: the console text must
be identical. The .fprg files next to the programs must be what the converter makes of them today.
"""
import contextlib
import io
import os
import re
import sys
import unittest
from unittest.mock import patch

EXAMPLES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPOSITORY = os.path.dirname(EXAMPLES)
sys.path[:0] = [os.path.join(REPOSITORY, "converter"), os.path.join(REPOSITORY, "library")]

import fprg_lint  # noqa: E402
import fprg_run  # noqa: E402
from py2fprg import convert_file, is_program_file  # noqa: E402


def play(*answers: str, randoms=(), shows=()):
    """One run: the typed answers, the values Random() returns, texts the console must show."""
    return list(answers), list(randoms), list(shows)


# every program, with the runs it is played with
RUNS = {
    "guess_number.py": [
        # Random(100) gives 41: the secret is 42
        play("50", "25", "42", randoms=[41], shows=["Too high.", "Too low.", "You needed 3 tries. Excellent!"]),
        play("50", "75", "90", "95", "99", "100", randoms=[99], shows=["You needed 6 tries. Good."]),
        play(*[str(n) for n in range(1, 12)], randoms=[10], shows=["You needed 11 tries. Keep practising."]),
    ],
    "arith_quiz/quiz.py": [
        # Random(3) + 1 picks the operation (1 add, 2 multiply, 3 subtract), Random(12) + 1 the numbers
        play("Ada", "2", "5", "12", "n", randoms=[0, 1, 2, 1, 2, 3],
             shows=["Question 1: 2 + 3 = ?", "Question 2: 3 x 4 = ?", "Ada, you scored 2 points out of 2 (100%).",
                    "Your grade: A", "Results: **", "Goodbye!"]),
        play("Bob", "0", "11", "1", "99", "y", "1", "5", "maybe", "no", randoms=[0, 1, 2, 0, 1, 2],
             shows=["Please enter a number from 1 to 10.", "Sorry, the answer is 5.",
                    "Bob, you scored 0 points out of 1 (0%).", "Your grade: F", "Results: -",
                    "Bob, you scored 1 point out of 1 (100%).", "Results: *"]),
        play("Cy", "3", "-11", "100", "11", "N", randoms=[2, 0, 11, 1, 11, 11, 2, 11, 0],
             shows=["Question 1: 1 - 12 = ?", "Question 2: 12 x 12 = ?", "Sorry, the answer is 144.",
                    "Question 3: 12 - 1 = ?", "Results: *-*", "Cy, you scored 2 points out of 3 (66%).",
                    "Your grade: C"]),
    ],
    "exercises/binary.py": [play("0"), play("10"), play("255")],
    "exercises/bubble.py": [play("5", "3", "9", "-1", "3")],
    "exercises/caesar.py": [play("Hello, World!", "3"), play("xyz", "25"), play("", "5")],
    "exercises/fib.py": [play("10"), play("0"), play("1")],
    "exercises/fizzbuzz.py": [play("15", shows=["FizzBuzz"]), play("0")],
    "exercises/gcd.py": [play("12", "18", shows=["gcd = 6 = 6", "lcm = 36"]), play("7", "0"), play("0", "5")],
    "exercises/grades.py": [play("95", "85", "72", "61", "10", "-1"), play("-1")],
    "exercises/menu.py": [play("1", "2", "3", "2", "2.5", "4", "3", "2", "10", "9", "0"), play("0")],
    "exercises/palindrome.py": [play("level", shows=["level is a palindrome"]), play("abc"), play(""), play("a")],
    "exercises/primes.py": [play("30", shows=["10 primes"]), play("2"), play("1")],
    "exercises/search.py": [play("15", shows=["15 is at index 2"]), play("7"), play("42")],
    "exercises/stats.py": [play("0", "101", "4", "1.5", "-2", "10", "3"), play("1", "7")],
    "exercises/table.py": [play("3")],
    "exercises/vowels.py": [play("hello world", shows=["3 vowels"]), play("")],
    "exercises/words.py": [play("the quick brown fox", shows=["4 words"]), play("  spaced   out  "), play(""),
                           play("one")],
}


def run_python(path: str, answers: list, randoms: list) -> str:
    """Run the program's main() with the flowgorithm library, scripted answers and Random() values."""
    with open(path, encoding="utf-8") as fh:
        code = compile(fh.read(), path, "exec")
    typed, rolls = iter(answers), iter(randoms)

    def read(prompt=""):
        try:
            return next(typed)
        except StopIteration:
            raise EOFError("the scripted answers ran out") from None

    namespace = {"__name__": "example"}
    out = io.StringIO()
    with patch("builtins.input", side_effect=read), \
            patch("random.randrange", side_effect=lambda n: next(rolls) % n), contextlib.redirect_stdout(out):
        exec(code, namespace)
        namespace["main"]()
    return out.getvalue()


def without_attributes(xml: str) -> str:
    """The document without its <attribute> lines (author, dates)."""
    return re.sub(r"\s*<attribute [^>]*/>", "", xml)


class ExamplesTest(unittest.TestCase):
    def test_every_program_is_played(self):
        programs = sorted(os.path.relpath(os.path.join(folder, f), EXAMPLES).replace(os.sep, "/")
                          for folder, _, files in os.walk(EXAMPLES) for f in files
                          if is_program_file(os.path.join(folder, f)))
        self.assertEqual(programs, sorted(RUNS))

    def test_python_and_flowchart_print_the_same(self):
        for name, runs in RUNS.items():
            path = os.path.join(EXAMPLES, name)
            xml = convert_file(path, metadata=False)
            self.assertEqual([f for f in fprg_lint.lint_string(xml, name) if f.severity == "ERROR"], [])
            for answers, randoms, shows in runs:
                with self.subTest(program=name, answers=answers):
                    text = run_python(path, answers, randoms)
                    for piece in shows:
                        self.assertIn(piece, text)
                    self.assertEqual(text, fprg_run.run_string(xml, answers, random_values=randoms))

    def test_the_flowcharts_are_up_to_date(self):
        for name in RUNS:
            with self.subTest(program=name):
                with open(os.path.splitext(os.path.join(EXAMPLES, name))[0] + ".fprg", encoding="utf-8") as fh:
                    saved = fh.read()
                made = convert_file(os.path.join(EXAMPLES, name))
                self.assertEqual(without_attributes(saved), without_attributes(made),
                                 f"regenerate it: py2fprg examples/{name}")


if __name__ == "__main__":
    unittest.main()
