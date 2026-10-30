import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from prompts import ask_int, ask_yes_no, is_yes, is_yes_or_no


class YesNoParsingTest(unittest.TestCase):
    def test_is_yes(self):
        self.assertTrue(is_yes("y"))
        self.assertTrue(is_yes("Yes please"))
        self.assertFalse(is_yes("no"))
        self.assertFalse(is_yes(""))

    def test_is_yes_or_no(self):
        for answer in ("y", "Y", "n", "N", "yes", "Nope"):
            self.assertTrue(is_yes_or_no(answer), answer)
        for answer in ("", "maybe", "1"):
            self.assertFalse(is_yes_or_no(answer), answer)


class AskIntTest(unittest.TestCase):
    def test_accepts_value_in_range(self):
        with patch("builtins.input", side_effect=["7"]):
            self.assertEqual(ask_int("How many?", 1, 10), 7)

    def test_repeats_until_in_range(self):
        out = io.StringIO()
        with patch("builtins.input", side_effect=["0", "11", "3"]), redirect_stdout(out):
            self.assertEqual(ask_int("How many?", 1, 10), 3)
        self.assertEqual(out.getvalue().count("Please enter a number from 1 to 10."), 2)


class AskYesNoTest(unittest.TestCase):
    def test_yes_and_no(self):
        with patch("builtins.input", side_effect=["yes"]):
            self.assertTrue(ask_yes_no("Again?"))
        with patch("builtins.input", side_effect=["N"]):
            self.assertFalse(ask_yes_no("Again?"))

    def test_repeats_on_garbage(self):
        with patch("builtins.input", side_effect=["", "maybe", "y"]):
            self.assertTrue(ask_yes_no("Again?"))


if __name__ == "__main__":
    unittest.main()
