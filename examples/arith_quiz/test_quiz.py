"""Unit tests for quiz.py (run: cd examples/arith_quiz && python3 -m unittest -v).

The tests are ordinary Python: they call the program's functions directly and play whole
games with scripted answers (Input() reads with input(), Random() uses random.randrange).
py2fprg never converts this file.
"""
import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(os.path.dirname(os.path.dirname(HERE)), "library"))  # the flowgorithm library

import quiz  # noqa: E402


def play(answers, randoms) -> str:
    """Run main() with the typed answers and the given Random() values; returns the console text."""
    out = io.StringIO()
    rolls = iter(randoms)
    with patch("builtins.input", side_effect=answers), \
            patch("random.randrange", side_effect=lambda n: next(rolls) % n), contextlib.redirect_stdout(out):
        quiz.main()
    return out.getvalue()


class FunctionsTest(unittest.TestCase):
    def test_questions_and_answers(self):
        self.assertEqual(quiz.question_text(quiz.ADD, 2, 3), "2 + 3 = ?")
        self.assertEqual(quiz.question_text(quiz.MULTIPLY, 7, 8), "7 x 8 = ?")
        self.assertEqual(quiz.correct_answer(quiz.SUBTRACT, 1, 12), -11)

    def test_grades(self):
        self.assertEqual(quiz.percentage(2, 3), 66)
        self.assertEqual(quiz.percentage(0, 0), 0)
        self.assertEqual([quiz.grade(p) for p in (95, 80, 50, 10)], ["A", "B", "C", "F"])
        self.assertEqual(quiz.plural(1, "point"), "1 point")
        self.assertEqual(quiz.plural(3, "point"), "3 points")

    def test_yes_no(self):
        self.assertTrue(quiz.is_yes("Yes"))
        self.assertFalse(quiz.is_yes(""))
        self.assertTrue(quiz.is_yes_or_no("no"))
        self.assertFalse(quiz.is_yes_or_no("maybe"))


class GameTest(unittest.TestCase):
    def test_one_round_all_correct(self):
        # Random(3) -> kind 1 + 0 = ADD, then a = 1 + 1, b = 1 + 2: "2 + 3"; next kind 2 (x): 3 x 4
        text = play(["Ada", "2", "5", "12", "n"], [0, 1, 2, 1, 2, 3])
        self.assertIn("Question 1: 2 + 3 = ?", text)
        self.assertIn("Question 2: 3 x 4 = ?", text)
        self.assertIn("Ada, you scored 2 points out of 2 (100%).", text)
        self.assertIn("Results: **", text)
        self.assertTrue(text.endswith("Goodbye!\n"))

    def test_validation_and_a_second_game(self):
        text = play(["Bob", "0", "11", "1", "99", "maybe", "y", "1", "5", "no"], [0, 1, 2, 0, 1, 2])
        self.assertIn("Please enter a number from 1 to 10.", text)
        self.assertIn("Sorry, the answer is 5.", text)
        self.assertIn("Bob, you scored 0 points out of 1 (0%).", text)
        self.assertIn("Bob, you scored 1 point out of 1 (100%).", text)


if __name__ == "__main__":
    unittest.main()
