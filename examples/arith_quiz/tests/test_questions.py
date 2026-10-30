import unittest

from questions import (ADD, MULTIPLY, SUBTRACT, correct_answer, grade, percentage, plural,
                       question_text)


class QuestionTextTest(unittest.TestCase):
    def test_each_kind(self):
        self.assertEqual(question_text(ADD, 2, 3), "2 + 3 = ?")
        self.assertEqual(question_text(SUBTRACT, 9, 4), "9 - 4 = ?")
        self.assertEqual(question_text(MULTIPLY, 7, 8), "7 x 8 = ?")


class CorrectAnswerTest(unittest.TestCase):
    def test_each_kind(self):
        self.assertEqual(correct_answer(ADD, 2, 3), 5)
        self.assertEqual(correct_answer(SUBTRACT, 9, 4), 5)
        self.assertEqual(correct_answer(MULTIPLY, 7, 8), 56)


class GradingTest(unittest.TestCase):
    def test_percentage(self):
        self.assertEqual(percentage(3, 4), 75)
        self.assertEqual(percentage(2, 3), 66)
        self.assertEqual(percentage(0, 0), 0)

    def test_grade_boundaries(self):
        self.assertEqual(grade(100), "A")
        self.assertEqual(grade(90), "A")
        self.assertEqual(grade(89), "B")
        self.assertEqual(grade(75), "B")
        self.assertEqual(grade(74), "C")
        self.assertEqual(grade(50), "C")
        self.assertEqual(grade(49), "F")

    def test_plural(self):
        self.assertEqual(plural(1, "point"), "1 point")
        self.assertEqual(plural(0, "point"), "0 points")
        self.assertEqual(plural(3, "point"), "3 points")


if __name__ == "__main__":
    unittest.main()
