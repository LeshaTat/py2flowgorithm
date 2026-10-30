"""Tests for the flowgorithm library (run: python3 -m unittest tests.test_flowgorithm -v).

The library is what student programs run with, so it must behave like Flowgorithm: the same
console text as fprg_run (the reference interpreter for the generated flowcharts), the same
conversions, the same run-time errors.
"""
import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowgorithm as fg  # noqa: E402
import fprg_run  # noqa: E402


def output(*values, **kw) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fg.Output(*values, **kw)
    return out.getvalue()


def read(kind, line: str):
    with patch("builtins.input", return_value=line):
        return fg.Input(kind)


class OutputTest(unittest.TestCase):
    def test_values_are_joined_like_ampersand(self):
        self.assertEqual(output("Total: ", 6), "Total: 6\n")
        self.assertEqual(output("a", "b", newline=False), "ab")
        self.assertEqual(output(), "\n")

    def test_numbers_and_booleans_print_like_flowgorithm(self):
        self.assertEqual(output(2.0, " ", 2.5, " ", -0.0, " ", True, " ", False), "2 2.5 0 true false\n")
        self.assertEqual(output(1e16), "1E+16\n")
        # .NET writes an exponent from 1E+15 on (Python's repr only from 1e+16)
        self.assertEqual(output(1e15, " ", -1.5e15, " ", 999999999999999.0), "1E+15 -1.5E+15 999999999999999\n")
        self.assertEqual(output(0.1 + 0.2), "0.30000000000000004\n")

    def test_arrays_cannot_be_output(self):
        with self.assertRaises(fg.FlowgorithmError):
            output([1, 2])


class InputTest(unittest.TestCase):
    def test_types(self):
        self.assertEqual(read(int, " 42 "), 42)
        self.assertEqual(read(float, "2.5"), 2.5)
        self.assertEqual(read(str, "  hi "), "  hi ")
        self.assertEqual(read(bool, "TRUE"), True)
        self.assertEqual(fg.Input.__defaults__, (str,))

    def test_bad_input_stops_like_flowgorithm(self):
        for kind, line in ((int, "3.0"), (int, "x"), (float, "abc"), (bool, "yes")):
            with self.subTest(kind=kind, line=line), self.assertRaises(fg.FlowgorithmError):
                read(kind, line)


class FunctionsTest(unittest.TestCase):
    def test_math(self):
        self.assertEqual(fg.Int(3.7), 3)
        self.assertEqual(fg.Int(-3.7), -3)
        self.assertEqual(fg.Abs(-2), 2)
        self.assertEqual(fg.Sgn(-0.5), -1)
        self.assertEqual(fg.Sqrt(9), 3.0)
        self.assertAlmostEqual(fg.Ln(fg.pi), 1.1447298858494002)
        self.assertEqual(fg.Log10(1000), 3.0)

    def test_strings_and_conversions(self):
        self.assertEqual(fg.Len("abc"), 3)
        self.assertEqual(fg.Char("abc", 1), "b")
        self.assertEqual(fg.ToCode("A"), 65)
        self.assertEqual(fg.ToChar(97), "a")
        self.assertEqual(fg.ToFixed(2.5, 2), "2.50")
        self.assertEqual(fg.ToInteger("-12"), -12)
        self.assertEqual(fg.ToReal("2.5"), 2.5)
        self.assertEqual(fg.ToString(3.0), "3")
        self.assertEqual(fg.Size([0] * 4), 4)

    def test_random(self):
        values = {fg.Random(3) for _ in range(200)}
        self.assertEqual(values, {0, 1, 2})
        with patch("random.randrange", return_value=1):  # programs' tests script it like this
            self.assertEqual(fg.Random(6), 1)

    def test_run_time_errors(self):
        for call in (lambda: fg.Char("ab", 2), lambda: fg.ToCode(""), lambda: fg.Sqrt(-1), lambda: fg.Random(0),
                     lambda: fg.Ln(0), lambda: fg.Arcsin(2), lambda: fg.ToInteger("1.5"), lambda: fg.Len(5),
                     lambda: fg.Size("abc"), lambda: fg.Char("ab", 1.0),
                     # the conversions take what Flowgorithm documents: text, or a number for ToString
                     lambda: fg.ToInteger(7.9), lambda: fg.ToReal(5), lambda: fg.ToString(True),
                     lambda: fg.ToString("x")):
            with self.assertRaises(fg.FlowgorithmError):
                call()


class SameAsInterpreterTest(unittest.TestCase):
    """The library gives what fprg_run (and so the generated flowchart) gives."""

    CASES = ["Int(-7 / 2)", "Abs(-2.5)", "Sgn(0)", "Sqrt(2)", "ToFixed(2.675, 2)", "ToFixed(1, 3)",
             "ToString(2.0)", "ToString(0.1)", "ToInteger(\"42\")", "ToReal(\"1e3\")", "Len(\"hello\")", "Char(\"hello\", 4)", "ToCode(\"z\")", "ToChar(65)",
             "Log(10)", "Log10(2)", "Arctan(1)", "Cos(pi)"]

    def test_functions(self):
        for case in self.CASES:
            with self.subTest(case=case):
                python = case.replace("true", "True").replace("pi", "fg.pi")
                ours = eval("fg." + python if not python.startswith("fg.") else python, {"fg": fg})
                self.assertEqual(ours, fprg_run.evaluate(case))

    def test_formatting(self):
        for value in (0, -5, 2.0, 2.5, 1 / 3, 1e15, -2.5e15, 1234567890123456.8, 1e16, 123456789.0, True, "x"):
            with self.subTest(value=value):
                self.assertEqual(output(value), fprg_run.format_value(value) + "\n")


if __name__ == "__main__":
    unittest.main()
