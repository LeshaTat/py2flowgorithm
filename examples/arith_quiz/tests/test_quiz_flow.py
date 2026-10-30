"""End-to-end test of the interactive program with scripted input and a fixed random sequence."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import quiz
from questions import ADD, MULTIPLY


class QuizFlowTest(unittest.TestCase):
    def run_quiz(self, inputs, randoms):
        out = io.StringIO()
        with patch("builtins.input", side_effect=inputs), \
                patch("random.randint", side_effect=randoms), redirect_stdout(out):
            quiz.main()
        return out.getvalue()

    def test_one_round_all_correct(self):
        # name, number of questions, 2 answers, play again?
        inputs = ["Ada", "2", "5", "12", "n"]
        randoms = [ADD, 2, 3,          # 2 + 3 = 5
                   MULTIPLY, 3, 4]     # 3 x 4 = 12
        output = self.run_quiz(inputs, randoms)
        self.assertIn("Welcome to the arithmetic quiz!", output)
        self.assertEqual(output.count("Correct!"), 2)
        self.assertIn("Results: **", output)
        self.assertIn("Ada, you scored 2 points out of 2 (100%).", output)
        self.assertIn("Your grade: A", output)
        self.assertIn("Goodbye!", output)

    def test_wrong_answer_and_second_round(self):
        inputs = ["Bob", "1", "99", "y", "1", "5", "no"]
        randoms = [ADD, 2, 3, ADD, 2, 3]
        output = self.run_quiz(inputs, randoms)
        self.assertIn("Sorry, the answer is 5.", output)
        self.assertIn("Results: -", output)
        self.assertIn("Bob, you scored 0 points out of 1 (0%).", output)
        self.assertIn("Your grade: F", output)
        self.assertIn("Results: *", output)
        self.assertIn("Bob, you scored 1 point out of 1 (100%).", output)

    def test_summary_helper_matches_printed_summary(self):
        results = [True, False, True]
        self.assertEqual(quiz.summary_string(results), "*-*")
        out = io.StringIO()
        with redirect_stdout(out):
            quiz.show_summary(results)
        self.assertEqual(out.getvalue().strip(), "Results: *-*")


if __name__ == "__main__":
    unittest.main()
