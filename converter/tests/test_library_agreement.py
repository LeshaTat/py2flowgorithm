"""The flowgorithm library and fprg_run agree (run from the repository root:
python3 -m unittest discover -s converter/tests).

Student programs run with the library (library/flowgorithm.py); their flowcharts are checked
with fprg_run. Both model Flowgorithm's run-time rules, so they must give the same values and
print the same text, or the Python-against-flowchart comparisons would prove nothing.
"""
import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(1, os.path.join(os.path.dirname(ROOT), "library"))  # the flowgorithm library

import flowgorithm as fg  # noqa: E402
import fprg_run  # noqa: E402


def output(*values) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fg.Output(*values)
    return out.getvalue()


class LibraryAgreesWithInterpreterTest(unittest.TestCase):
    """The library gives what fprg_run (and so the generated flowchart) gives."""

    CASES = ["Int(-7 / 2)", "Abs(-2.5)", "Sgn(0)", "Sqrt(2)", "ToFixed(2.675, 2)", "ToFixed(1, 3)",
             "ToString(2.0)", "ToString(0.1)", "ToInteger(\"42\")", "ToReal(\"1e3\")", "Len(\"hello\")",
             "Char(\"hello\", 4)", "ToCode(\"z\")", "ToChar(65)", "Log(10)", "Log10(2)", "Arctan(1)", "Cos(pi)"]

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
