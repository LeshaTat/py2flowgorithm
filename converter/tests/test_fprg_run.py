"""Tests for fprg_run, the headless .fprg interpreter (run: python3 -m unittest tests.test_fprg_run -v).

Four groups: the expression evaluator, hand-written programs for every statement type,
real files saved by Flowgorithm (skipped when the sample folder is not present), and
differential tests that run the example Python programs and their py2fprg conversions
with the same scripted input and random values and compare the console output.
"""
import html
import io
import math
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

import fprg_run  # noqa: E402
from fprg_run import (FArray, FprgRuntimeError, FprgSyntaxError, Machine, evaluate,  # noqa: E402
                      format_value, run_file, run_string)

# Files saved by Flowgorithm itself (third-party data, read only). Override with FPRG_SAMPLES.
SAMPLES = os.environ.get("FPRG_SAMPLES") or (
    "/private/tmp/claude-501/-Users-alekseitatuzov-personal-code-flowgorithm/"
    "57e2f65b-ae8d-445f-9316-7777c7d50473/scratchpad/samples_all")


# ---------------------------------------------------------------------------
# Tiny XML builders so the hand-written programs stay readable
# ---------------------------------------------------------------------------

def q(text: str) -> str:
    return html.escape(text, quote=True)


def decl(names, vtype, array=False, size=""):
    return f'<declare name="{q(names)}" type="{vtype}" array="{"True" if array else "False"}" size="{q(size)}"/>'


def assign(var, expr):
    return f'<assign variable="{q(var)}" expression="{q(expr)}"/>'


def inp(var):
    return f'<input variable="{q(var)}"/>'


def out(expr, newline=True):
    return f'<output expression="{q(expr)}" newline="{"True" if newline else "False"}"/>'


def if_(cond, then, else_=""):
    return f'<if expression="{q(cond)}"><then>{then}</then><else>{else_}</else></if>'


def while_(cond, body):
    return f'<while expression="{q(cond)}">{body}</while>'


def do_(cond, body):
    return f'<do expression="{q(cond)}">{body}</do>'


def for_(var, start, end, body, direction="inc", step="1"):
    return (f'<for variable="{q(var)}" start="{q(start)}" end="{q(end)}" direction="{direction}" '
            f'step="{q(step)}">{body}</for>')


def call(expr):
    return f'<call expression="{q(expr)}"/>'


def param(name, ptype, array=False):
    return f'<parameter name="{name}" type="{ptype}" array="{"True" if array else "False"}"/>'


def func(name, ftype, variable, params, body):
    return (f'<function name="{name}" type="{ftype}" variable="{variable}"><parameters>{params}</parameters>'
            f'<body>{body}</body></function>')


def prog(main_body, functions="", fileversion="3.0"):
    return (f'<?xml version="1.0"?>\n<flowgorithm fileversion="{fileversion}">\n'
            f'<attributes><attribute name="name" value="test"/></attributes>\n'
            f'<function name="Main" type="None" variable=""><parameters/><body>{main_body}</body></function>'
            f'{functions}</flowgorithm>\n')


def run(main_body, inputs=(), functions="", **kw):
    return run_string(prog(main_body, functions), inputs, **kw)


# ---------------------------------------------------------------------------
# 1. Expression evaluator
# ---------------------------------------------------------------------------

class ExpressionTest(unittest.TestCase):
    def check(self, text, want, variables=None):
        got = evaluate(text, variables)
        self.assertEqual(got, want, text)
        self.assertIs(type(got), type(want), f"{text}: type {type(got).__name__}, want {type(want).__name__}")

    def test_precedence(self):
        self.check("1 + 3 ^ 2", 10)
        self.check("2 * 3 ^ 2", 18)
        self.check("6 / 3 * 2", 4.0)
        self.check("10 mod 3", 1)
        self.check("10 % 3", 1)
        self.check("-2 ^ 2", 4)              # unary minus binds tighter than ^
        self.check("-2 ^ 2 + 1", 5)
        self.check("2 ^ -1", 0.5)
        self.check("1 & 2 + 3", "15")        # & is below + ...
        self.check("1 + 2 & 3", "33")
        self.check("1 + 2 = 3 and 2 > 1", True)   # ... and above the relational operators
        self.check("not true or true", True)
        self.check("not (true or true)", False)
        self.check("1 < 2 == true", True)    # chained comparisons are left-associative

    def test_unicode_and_basic_spellings(self):
        self.check("3 × 2 ÷ 4", 1.5)
        self.check("2 ↑ 3", 8)
        self.check("5 ≥ 4 ∧ ¬ false", True)
        self.check("1 ≠ 2 ∨ false", True)
        self.check("3 ≤ 3 && 2 <> 3 || false", True)
        self.check("!true", False)
        self.check("3 = 3.0", True)
        self.check("π > 3.14 and Pi < 3.15 and PI == pi", True)

    def test_types_of_arithmetic(self):
        self.check("7 / 2", 3.5)
        self.check("4 / 2", 2.0)             # division is always Real
        self.check("Int(7 / 2)", 3)
        self.check("2 + 3", 5)
        self.check("2 + 3.0", 5.0)
        self.check("2 ^ 10", 1024)
        self.check("2.0 ^ 2", 4.0)
        self.check("7 % -3", 1)              # remainder takes the sign of the dividend (a guess)
        self.check("7.5 % 2", 1.5)
        with self.assertRaises(FprgRuntimeError):  # checked in Flowgorithm: '-7' is not valid for % mod
            evaluate("-7 % 3")
        self.check("1e3 + 1", 1001.0)

    def test_concatenation_formats_like_output(self):
        self.check('"a" & 1 & true', "a1true")
        self.check('"x=" & 2.5 & "/" & 3.0 & "/" & false', "x=2.5/3/false")

    def test_strings_and_comparisons(self):
        self.check('"abc" < "abd"', True)
        self.check('"b" > "a" and "a" == "a" and "a" != "b"', True)
        self.check("true == true and false != true", True)

    def test_intrinsics(self):
        self.check('Char("abc", 1)', "b")
        self.check('Len("hello")', 5)
        self.check("ToFixed(3.14159, 2)", "3.14")
        self.check("ToFixed(2, 3)", "2.000")
        self.check("Int(-2.7)", -2)
        self.check("Int(2.7)", 2)
        self.check("Abs(-3)", 3)
        self.check("Abs(-2.5)", 2.5)
        self.check("Sgn(-9)", -1)
        self.check("Sgn(0)", 0)
        self.check("Sqrt(16)", 4.0)
        self.check("Ln(1)", 0.0)
        self.check("Log10(1000)", 3.0)
        self.check("Sin(0) + Cos(0) + Tan(0)", 1.0)
        self.check("Arctan(1) * 4", math.pi)
        self.check("Arcsin(1) * 2 == Arccos(0) * 2", True)
        self.check("ToChar(65) & ToCode(\"A\")", "A65")
        self.check('ToInteger("42") + ToInteger(3.9)', 45)
        self.check('ToReal("1.5") + ToReal(1)', 2.5)
        self.check("ToString(2.50) & ToString(7) & ToString(true)", "2.57true")
        self.check("EOF()", True)

    def test_intrinsics_are_case_insensitive(self):
        self.check('len("ab") + LEN("c") + Len("d")', 4)
        self.check("sqrt(4) + SQRT(9)", 5.0)

    def test_random_with_fixed_sequence(self):
        self.assertEqual(evaluate("Random(6)", random_values=[7]), 1)       # 7 % 6
        self.assertEqual(evaluate("Random(6) & Random(6)", random_values=[7, 8]), "12")
        self.assertEqual(evaluate("Random(10)", random_values=[3]), 3)
        with self.assertRaises(FprgRuntimeError) as cm:
            evaluate("Random(6) + Random(6)", random_values=[1])
        self.assertIn("exhausted", str(cm.exception))

    def test_random_with_seed_is_reproducible_and_in_range(self):
        a = [evaluate("Random(6)", seed=12345) for _ in range(5)]
        b = [evaluate("Random(6)", seed=12345) for _ in range(5)]
        self.assertEqual(a, b)
        m = Machine(fprg_run._EMPTY_PROGRAM_XML, seed=7)
        values = [m.evaluate("Random(6)") for _ in range(200)]
        self.assertTrue(all(0 <= v < 6 for v in values))
        self.assertEqual(len(set(values)), 6)

    def test_variables(self):
        self.check("x * 2 + a[1] & s", "8.5!", {"x": 3, "a": [1.5, 2.5], "s": "!"})
        self.check("Size(a)", 3, {"a": [1, 2, 3]})
        self.check("flag or X > 1", True, {"flag": False, "x": 2})   # case-insensitive lookup

    def test_errors(self):
        def err(text, *fragments, variables=None):
            with self.assertRaises(FprgRuntimeError) as cm:
                evaluate(text, variables)
            for f in fragments:
                self.assertIn(f, str(cm.exception), text)

        err('1 + "a"', "'+'", "use '&'")
        err("x", "variable 'x' is not declared")
        err('Char("abc", 5)', "Char()", "out of range")
        err("Len(1, 2)", "Len() takes 1 argument(s), 2 given")
        err("Foo(1)", "unknown function 'Foo'")
        err("1 / 0", "division by zero")
        err("5 % 0", "division by zero")
        err("10 ^ 400 + 0.5", "overflow in '+'")
        err("10.0 ^ 400", "overflow in '^'")
        err("0 ^ -1", "negative power")
        err("true + 1", "needs numbers")
        err('1 < "a"', "cannot compare")
        err("true < false", "cannot compare")
        err("not 1", "needs a Boolean")
        err("1 and true", "must be Boolean")
        err("(-8) ^ 0.5", "no real value")
        err("a[3]", "index 3 is out of range", variables={"a": [1, 2]})
        err("a[1.0]", "must be an Integer", variables={"a": [1, 2]})
        err("Random(0)", "positive Integer")
        err("Sqrt(-1)", "negative")
        err("Size(3)", "needs an array")
        err("ToInteger(\"4.5\")", "cannot convert")
        err("a + 1", "array", variables={"a": [1]})

    def test_syntax_errors(self):
        for text in ("1 +", "(1 + 2", '"open', "1 2", "a[1, 2]", "+1", "1.", "my_var + 1", "1 $ 2"):
            with self.assertRaises(FprgSyntaxError, msg=text):
                evaluate(text)

    def test_short_circuit(self):
        self.check('Len(s) > 0 and Char(s, 0) == "y"', False, {"s": ""})
        self.check('Len(s) == 0 or Char(s, 0) == "y"', True, {"s": ""})


class FormatTest(unittest.TestCase):
    def test_format_value(self):
        self.assertEqual(format_value(12), "12")
        self.assertEqual(format_value(-3), "-3")
        self.assertEqual(format_value(3.0), "3")           # whole-valued Real prints like an integer
        self.assertEqual(format_value(-0.0), "0")
        self.assertEqual(format_value(2.5), "2.5")
        self.assertEqual(format_value(0.1), "0.1")
        self.assertEqual(format_value(1 / 3), "0.3333333333333333")
        self.assertEqual(format_value(1e16), "1E+16")
        self.assertEqual(format_value(1.5e-7), "1.5E-07")
        self.assertEqual(format_value(True), "true")
        self.assertEqual(format_value(False), "false")
        self.assertEqual(format_value("text"), "text")
        with self.assertRaises(FprgRuntimeError):
            format_value(FArray([1], "Integer"))


# ---------------------------------------------------------------------------
# 2. Hand-written programs: every statement type
# ---------------------------------------------------------------------------

class StatementTest(unittest.TestCase):
    def test_declare_defaults_and_output(self):
        body = (decl("n", "Integer") + decl("r", "Real") + decl("s", "String") + decl("b", "Boolean")
                + out('n & "|" & r & "|" & s & "|" & b'))
        self.assertEqual(run(body), "0|0||false\n")

    def test_declare_comma_list_and_case_insensitive_names(self):
        body = decl("Count, Total", "Integer") + assign("count", "3") + assign("TOTAL", "COUNT * 2") + out("Total")
        self.assertEqual(run(body), "6\n")

    def test_assign_conversions(self):
        body = (decl("n", "Integer") + decl("r", "Real")
                + assign("r", "7") + out("r / 2")                      # Integer -> Real
                + assign("n", "7.9") + out("n")                        # Real -> Integer truncates
                + assign("n", "-7.9") + out("n")
                + assign("n", "9 / 3") + out("n"))                     # / is Real, truncated on assignment
        self.assertEqual(run(body), "3.5\n7\n-7\n3\n")

    def test_assign_type_errors(self):
        for target_type, expr in (("Integer", '"5"'), ("String", "5"), ("Boolean", "1"), ("Real", "true")):
            with self.assertRaises(FprgRuntimeError, msg=expr) as cm:
                run(decl("x", target_type) + assign("x", expr))
            self.assertIn("cannot assign", str(cm.exception))

    def test_output_without_newline(self):
        body = out('"a"', newline=False) + out('"b"', newline=False) + out('"c"') + out("1 + 1")
        self.assertEqual(run(body), "abc\n2\n")

    def test_output_formats(self):
        body = out("3.0") + out("2.5") + out("10 / 4") + out("true") + out('"s"') + out("-0.5 * 2")
        self.assertEqual(run(body), "3\n2.5\n2.5\ntrue\ns\n-1\n")

    def test_if_then_else_nested(self):
        body = (decl("x", "Integer") + inp("x")
                + if_("x < 0", out('"negative"'),
                      if_("x == 0", out('"zero"'), out('"positive"'))))
        self.assertEqual(run(body, ["-3"]), "negative\n")
        self.assertEqual(run(body, ["0"]), "zero\n")
        self.assertEqual(run(body, ["8"]), "positive\n")

    def test_if_condition_must_be_boolean(self):
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("x", "Integer") + if_("x", out("1")))
        self.assertIn("must be Boolean", str(cm.exception))

    def test_while(self):
        body = (decl("i, sum", "Integer") + assign("i", "1")
                + while_("i <= 10", assign("sum", "sum + i") + assign("i", "i + 1"))
                + out('"sum=" & sum & " i=" & i'))
        self.assertEqual(run(body), "sum=55 i=11\n")

    def test_while_false_never_runs(self):
        self.assertEqual(run(while_("false", out('"never"')) + out('"done"')), "done\n")

    def test_do_runs_body_first_and_repeats_while_true(self):
        body = (decl("n", "Integer") + assign("n", "5")
                + do_("n > 0", out("n", newline=False) + assign("n", "n - 1")) + out('""')
                + do_("false", out('"once"')))
        self.assertEqual(run(body), "54321\nonce\n")

    def test_for_inc_with_step(self):
        body = (decl("i", "Integer") + for_("i", "1", "10", out("i", newline=False), step="2")
                + out('" after=" & i'))
        self.assertEqual(run(body), "13579 after=11\n")

    def test_for_dec(self):
        body = decl("i", "Integer") + for_("i", "5", "1", out("i", newline=False), direction="dec") + out('""')
        self.assertEqual(run(body), "54321\n")

    def test_for_inclusive_end_expression_evaluated_once(self):
        body = (decl("i, n", "Integer") + assign("n", "3")
                + for_("i", "0", "n - 1", out("i", newline=False) + assign("n", "100")) + out('""'))
        self.assertEqual(run(body), "012\n")

    def test_for_zero_iterations(self):
        body = decl("i", "Integer") + for_("i", "5", "1", out('"never"')) + out('"i=" & i')
        self.assertEqual(run(body), "i=5\n")

    def test_for_real_variable(self):
        body = decl("x", "Real") + for_("x", "0", "1", out("x", newline=False) + out('" "', newline=False),
                                        step="0.5") + out('""')
        self.assertEqual(run(body), "0 0.5 1 \n")

    def test_for_errors(self):
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("i", "Integer") + for_("i", "1", "3", "", step="0"))
        self.assertIn("step must be positive", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("s", "String") + for_("s", "1", "3", ""))
        self.assertIn("loop variable", str(cm.exception))

    def test_legacy_1_0_file(self):
        # Flowgorithm 1.0: <declare variables=...>, <output> without newline, <for> without direction
        xml = ('<?xml version="1.0"?>\n<flowgorithm fileversion="1.0"><attributes/>'
               '<function name="Main" type="None" variable=""><parameters/><body>'
               '<declare variables="n" type="Integer"/>'
               '<for variable="n" start="1" end="3" step="1"><output expression="n"/></for>'
               '</body></function></flowgorithm>')
        self.assertEqual(run_string(xml), "1\n2\n3\n")

    def test_arrays(self):
        body = (decl("n, i", "Integer") + inp("n") + decl("a", "Integer", array=True, size="n")
                + for_("i", "0", "Size(a) - 1", assign("a[i]", "(i + 1) * 10"))
                + inp("a[1]")                                            # input into an element
                + out("a[0] & \",\" & a[1] & \",\" & a[2] & \" size=\" & Size(a)"))
        m = Machine(prog(body), ["3", "7"])
        self.assertEqual(m.run(), "10,7,30 size=3\n")
        self.assertEqual(m.variables["a"], [10, 7, 30])
        self.assertEqual(m.variables["n"], 3)
        self.assertEqual(m.variables["i"], 3)

    def test_array_defaults_per_type(self):
        body = (decl("s", "String", array=True, size="2") + decl("r", "Real", array=True, size="1")
                + decl("b", "Boolean", array=True, size="1")
                + out('"[" & s[0] & s[1] & "]" & r[0] & b[0]'))
        self.assertEqual(run(body), "[]0false\n")

    def test_array_element_conversion(self):
        body = decl("r", "Real", array=True, size="1") + assign("r[0]", "3") + out("r[0] / 2")
        self.assertEqual(run(body), "1.5\n")
        with self.assertRaises(FprgRuntimeError):
            run(decl("n", "Integer", array=True, size="1") + assign("n[0]", '"x"'))

    def test_array_errors(self):
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("a", "Integer", array=True, size="2") + assign("a[2]", "1"))
        self.assertIn("index 2 is out of range for 'a' (size 2)", str(cm.exception))
        self.assertEqual(cm.exception.path, "Main/body[1]/assign")
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("a", "Integer", array=True, size="2") + assign("a", "1"))
        self.assertIn("is an array", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("x", "Integer") + out("x[0]"))
        self.assertIn("not an array", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("a", "Integer", array=True, size="2.5"))
        self.assertIn("array size", str(cm.exception))
        with self.assertRaises(FprgRuntimeError):
            run(decl("a", "Integer", array=True, size="2") + out("a"))

    def test_value_function_with_pi(self):
        circle = func("Circle", "Real", "Area", param("Radius", "Real"),
                      decl("Area", "Real") + assign("Area", "Pi * Radius ^ 2"))
        body = decl("x", "Integer") + assign("x", "2") + out('"Area is " & circle(x)')   # case-insensitive call
        self.assertEqual(run(body, functions=circle), f"Area is {math.pi * 4!r}\n")

    def test_function_returning_a_parameter(self):
        twice = func("Twice", "Integer", "n", param("n", "Integer"), assign("n", "n * 2"))
        self.assertEqual(run(out("Twice(21)"), functions=twice), "42\n")

    def test_function_result_conversion(self):
        f = func("Half", "Integer", "r", param("n", "Integer"), decl("r", "Real") + assign("r", "n / 2"))
        self.assertEqual(run(out("Half(7)"), functions=f), "3\n")

    def test_void_call_and_array_by_reference(self):
        fill = func("Fill", "None", "", param("arr", "Integer", array=True) + param("v", "Integer"),
                    decl("i", "Integer") + for_("i", "0", "Size(arr) - 1", assign("arr[i]", "v + i")))
        show = func("Show", "None", "", param("arr", "Integer", array=True),
                    decl("i", "Integer") + for_("i", "0", "Size(arr) - 1", out('arr[i] & " "', newline=False))
                    + out('""'))
        body = decl("a", "Integer", array=True, size="3") + call("Fill(a, 5)") + call("Show(a)")
        m = Machine(prog(body, fill + show))
        self.assertEqual(m.run(), "5 6 7 \n")
        self.assertEqual(m.variables["a"], [5, 6, 7])

    def test_parameters_are_local_and_converted(self):
        f = func("Show", "None", "", param("x", "Real"), assign("x", "x + 0.5") + out("x"))
        body = decl("x", "Integer") + assign("x", "1") + call("Show(x)") + out("x")
        self.assertEqual(run(body, functions=f), "1.5\n1\n")

    def test_recursion_factorial(self):
        fact = func("Fact", "Integer", "result", param("n", "Integer"),
                    decl("result", "Integer")
                    + if_("n <= 1", assign("result", "1"), assign("result", "n * Fact(n - 1)")))
        self.assertEqual(run(out("Fact(10)"), functions=fact), "3628800\n")
        self.assertEqual(run(out("Fact(0)"), functions=fact), "1\n")

    def test_recursion_depth_limit(self):
        forever = func("Forever", "Integer", "r", param("n", "Integer"),
                       decl("r", "Integer") + assign("r", "Forever(n + 1)"))
        with self.assertRaises(FprgRuntimeError) as cm:
            run_string(prog(out("Forever(1)"), forever), max_depth=50)
        self.assertIn("call depth exceeded 50", str(cm.exception))

    def test_function_errors(self):
        f = func("F", "Integer", "r", param("n", "Integer"), decl("r", "Integer") + assign("r", "n"))
        v = func("V", "None", "", "", out("1"))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(out("F(1, 2)"), functions=f)
        self.assertIn("'F' takes 1 argument(s), 2 given", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(out('F("x")'), functions=f)
        self.assertIn("parameter 'n' of F", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(out("V()"), functions=v)
        self.assertIn("returns no value", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(call("Nope()"))
        self.assertIn("unknown function 'Nope'", str(cm.exception))
        g = func("G", "Integer", "missing", "", out("1"))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(out("G()"), functions=g)
        self.assertIn("return variable 'missing'", str(cm.exception))
        self.assertEqual(cm.exception.function, "G")
        arr = func("A", "None", "", param("a", "Integer", array=True), out("Size(a)"))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("r", "Real", array=True, size="1") + call("A(r)"), functions=arr)
        self.assertIn("Integer array, got a Real array", str(cm.exception))

    def test_call_statement_with_value_function_discards_result(self):
        f = func("F", "Integer", "r", "", decl("r", "Integer") + out('"side effect"') + assign("r", "1"))
        self.assertEqual(run(call("F()"), functions=f), "side effect\n")

    def test_input_conversions(self):
        body = (decl("n", "Integer") + decl("r", "Real") + decl("b", "Boolean") + decl("s", "String")
                + inp("n") + inp("r") + inp("b") + inp("s") + out('n & "|" & r & "|" & b & "|" & s'))
        self.assertEqual(run(body, [" 42 ", "2.50", "TRUE", "  hi there "]), "42|2.5|true|  hi there \n")
        self.assertEqual(run(body, ["-1", "3", "false", ""]), "-1|3|false|\n")

    def test_input_errors(self):
        def err(vtype, text, *fragments):
            with self.assertRaises(FprgRuntimeError) as cm:
                run(decl("x", vtype) + inp("x"), [text])
            for f in fragments:
                self.assertIn(f, str(cm.exception))
            self.assertEqual(cm.exception.path, "Main/body[1]/input")

        err("Integer", "4.5", "input '4.5' is not an Integer")
        err("Integer", "abc", "not an Integer")
        err("Real", "abc", "not a Real")
        err("Boolean", "yes", "not a Boolean")
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("x", "Integer") + inp("x") + inp("x"), ["1"])
        self.assertIn("no input is left", str(cm.exception))
        self.assertIn("1 line(s) were consumed", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("x", "Integer") + inp("x[0]"), ["1"])
        self.assertIn("not an array", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("a", "Integer", array=True, size="1") + inp("a"), ["1"])
        self.assertIn("is an array", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("a", "Integer", array=True, size="1") + inp("a[1]"), ["1"])
        self.assertIn("out of range", str(cm.exception))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(decl("r", "Real") + assign("r", "10 ^ 400"))
        self.assertIn("too large", str(cm.exception))

    def test_inputs_may_be_an_iterator(self):
        body = decl("x", "Integer") + inp("x") + inp("x") + out("x")
        self.assertEqual(run(body, iter(["1", "2"])), "2\n")

    def test_comment_and_breakpoint_are_no_ops(self):
        body = '<comment text="hello&#13;&#10;world"/>' + out("1") + "<breakpoint/>" + out("2")
        self.assertEqual(run(body), "1\n2\n")

    def test_error_location(self):
        body = (decl("i", "Integer")
                + while_("i < 3", if_("i == 1", assign("missing", "1")) + assign("i", "i + 1")))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(body)
        e = cm.exception
        self.assertEqual(e.function, "Main")
        self.assertEqual(e.path, "Main/body[1]/while[0]/if/then[0]/assign")
        self.assertEqual(str(e), "variable 'missing' is not declared in function Main "
                                 "(in function Main, at Main/body[1]/while[0]/if/then[0]/assign)")

    def test_error_inside_function_reports_that_function(self):
        f = func("Boom", "None", "", param("n", "Integer"), out("n / 0"))
        with self.assertRaises(FprgRuntimeError) as cm:
            run(call("Boom(1)"), functions=f)
        self.assertEqual(cm.exception.function, "Boom")
        self.assertEqual(cm.exception.path, "Boom/body[0]/output")

    def test_max_steps(self):
        with self.assertRaises(FprgRuntimeError) as cm:
            run(while_("true", ""), max_steps=500)
        self.assertIn("more than 500 statements", str(cm.exception))
        m = Machine(prog(decl("i", "Integer") + while_("i < 10", assign("i", "i + 1"))))
        m.run()
        # declare, the while itself (its first test), then 10 x (assign + the next loop test)
        self.assertEqual(m.steps, 1 + 1 + 10 * 2)

    def test_redeclare_resets(self):
        body = (decl("i, x", "Integer")
                + for_("i", "1", "2", decl("x", "Integer") + out("x", newline=False) + assign("x", "9"))
                + out('""'))
        self.assertEqual(run(body), "00\n")

    def test_random_in_program(self):
        body = (decl("i", "Integer") + decl("r", "Integer", array=True, size="3")
                + for_("i", "0", "2", assign("r[i]", "1 + Random(6)")) + out("r[0] & r[1] & r[2]"))
        self.assertEqual(run(body, random_values=[0, 5, 6]), "161\n")
        self.assertEqual(run(body, seed=3), run(body, seed=3))
        out_text = run(body, seed=3)
        self.assertTrue(all(ch in "123456" for ch in out_text.strip()), out_text)

    def test_load_errors(self):
        with self.assertRaises(FprgSyntaxError) as cm:
            run_string("<flowgorithm><function name='Main' type='None' variable=''><body>"
                       "<forward expression='10'/></body></function></flowgorithm>")
        self.assertIn("unsupported statement <forward>", str(cm.exception))
        self.assertEqual(cm.exception.path, "Main/body[0]/forward")
        with self.assertRaises(FprgSyntaxError) as cm:
            run(decl("x", "Integer") + assign("x", "1 +"))
        self.assertIn("syntax error in expression '1 +'", str(cm.exception))
        self.assertEqual(cm.exception.path, "Main/body[1]/assign")
        with self.assertRaises(FprgSyntaxError):
            run_string("<flowgorithm></flowgorithm>")             # no Main
        with self.assertRaises(FprgSyntaxError):
            run_string("<html/>")
        with self.assertRaises(FprgSyntaxError):
            run_string("not xml at all")
        with self.assertRaises(FprgSyntaxError):
            run(call("x + 1"))                                    # call must be a function call
        with self.assertRaises(FprgSyntaxError):
            run(decl("x", "Integer") + '<assign variable="x + 1" expression="1"/>')

    def test_run_file_with_entities_and_crlf_in_expression(self):
        # as Flowgorithm writes it: numeric character references, CRLF inside a long expression
        body = (decl("s", "String") + '<assign variable="s" expression="&quot;caf&#233;&quot;"/>'
                + '<output expression="Len(s) &gt; 0&#13;&#10;  &amp;&amp; Char(s, 3) == &quot;&#233;&quot;" '
                  'newline="True"/>' + out("s"))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.fprg")
            with open(path, "w", encoding="ascii") as f:
                f.write(prog(body))
            self.assertEqual(run_file(path), "true\ncafé\n")

    def test_machine_variables_and_output(self):
        body = decl("a, b", "Integer") + decl("name", "String") + assign("a", "3") + assign("name", '"x"') + out("a")
        m = Machine(prog(body))
        self.assertEqual(m.output, "")
        m.run()
        self.assertEqual(m.output, "3\n")
        self.assertEqual(m.variables, {"a": 3, "b": 0, "name": "x"})
        self.assertEqual(list(m.variables), ["a", "b", "name"])

    def test_echo_stream(self):
        stream = io.StringIO()
        Machine(prog(out('"hi"') + out('"!"', newline=False)), echo=stream).run()
        self.assertEqual(stream.getvalue(), "hi\n!")


# ---------------------------------------------------------------------------
# 3. Real files saved by Flowgorithm
# ---------------------------------------------------------------------------

@unittest.skipUnless(os.path.isdir(SAMPLES), f"sample folder not present: {SAMPLES}")
class SampleFilesTest(unittest.TestCase):
    def sample(self, name, inputs=(), **kw):
        return run_file(os.path.join(SAMPLES, name), inputs, **kw)

    def test_max3numbers(self):
        self.assertEqual(self.sample("max3numbers.fprg", ["3", "9", "5"]), "9\n")
        self.assertEqual(self.sample("max3numbers.fprg", ["1.5", "-2", "7.25"]), "7.25\n")

    def test_next(self):
        self.assertEqual(self.sample("next.fprg", ["41"]), "Next is 42\n")

    def test_while_1_0(self):
        self.assertEqual(self.sample("While.fprg"), "".join(f"{n}\n" for n in range(1, 101)))

    def test_for_1_0(self):
        self.assertEqual(self.sample("For.fprg"), "".join(f"{n}\n" for n in range(1, 101)))

    def test_string_name(self):
        self.assertEqual(self.sample("String - Name.fprg", ["Ada"]), "A\nd\na\n")

    def test_function_circle(self):
        text = self.sample("Function - Circle.fprg", ["2"])
        self.assertEqual(text, f"Input the radius of the circle\nArea is {math.pi * 4!r}\n")
        self.assertTrue(text.startswith("Input the radius of the circle\nArea is 12.56637061435917"))

    def test_s14_array(self):
        text = self.sample("s14.fprg", ["3", "ann", "bob", "cy"])
        self.assertEqual(text, "Please enter the array size:\nFilled array : ann,bob,cy,\n")

    def test_guess_a_number(self):
        text = self.sample("guessANumber.fprg", ["50", "30", "42", "n"], random_values=[41])
        prompt = "What is your guess (1-100, 0 to give up)?\n"
        self.assertEqual(text, prompt + "Your guess of 50 is too high.\n" + prompt + "Your guess of 30 is too low.\n"
                         + prompt + "Correct!\nThe secret number was 42.\nPlay again (y/n)?\nThanks for playing!\n")
        text = self.sample("guessANumber.fprg", ["0", "y", "7", "N"], random_values=[6, 6])
        self.assertEqual(text, prompt + "You gave up!\nThe secret number was 7.\nPlay again (y/n)?\n"
                         + prompt + "Correct!\nThe secret number was 7.\nPlay again (y/n)?\nThanks for playing!\n")

    def test_other_samples_run(self):
        self.assertEqual(self.sample("Area of Circle.fprg", ["2"]),
                         "Please enter the radius of a circle\nThe area is 12.56\n")
        self.assertEqual(self.sample("Tip Calculator.fprg", ["20"]),
                         "How much is the bill?\nThe tip is $3\nThe total, with tax, is $23\n")
        self.assertEqual(self.sample("s11.fprg", ["5", "3"]).splitlines()[-1][-3:], " 40")   # 5!/3!*2! = 40
        self.assertTrue(self.sample("s07.fprg", ["3", "4"]).endswith("5\n"))               # hypotenuse
        self.assertEqual(self.sample("s06.fprg", ["1", "2", "3", "4", "5"]).splitlines()[-5:],
                         ["1", "4", "9", "16", "25"])


# ---------------------------------------------------------------------------
# 4. Command line
# ---------------------------------------------------------------------------

class CliTest(unittest.TestCase):
    SCRIPT = os.path.join(ROOT, "src", "fprg_run.py")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "prog.fprg")
        body = (decl("n, r", "Integer") + inp("n") + assign("r", "Random(10)")
                + out('"n=" & n & " r=" & r', newline=False))
        with open(self.path, "w") as f:
            f.write(prog(body))

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args, stdin=""):
        return subprocess.run([sys.executable, self.SCRIPT, *args], input=stdin, capture_output=True, text=True)

    def test_inputs_random_and_vars(self):
        r = self.cli(self.path, "--input", "5", "--random", "23", "--vars")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "n=5 r=3\n--- variables of Main ---\nn = 5\nr = 3\n")

    def test_stdin_and_seed(self):
        r = self.cli(self.path, "--seed", "1", stdin="7\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("n=7 r="))
        self.assertEqual(r.stdout, self.cli(self.path, "--seed", "1", stdin="7\n").stdout)

    def test_input_file(self):
        inputs = os.path.join(self.tmp.name, "in.txt")
        with open(inputs, "w") as f:
            f.write("9\n")
        r = self.cli(self.path, "--input-file", inputs, "--random", "0")
        self.assertEqual(r.stdout, "n=9 r=0")

    def test_runtime_error_exits_1(self):
        r = self.cli(self.path, "--input", "x")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout, "")
        self.assertIn("fprg_run: error: input 'x' is not an Integer", r.stderr)
        self.assertIn("at Main/body[1]/input", r.stderr)
        r = self.cli(self.path, stdin="")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no input is left", r.stderr)

    def test_max_steps_option(self):
        with open(self.path, "w") as f:
            f.write(prog(while_("true", "")))
        r = self.cli(self.path, "--max-steps", "100")
        self.assertEqual(r.returncode, 1)
        self.assertIn("more than 100 statements", r.stderr)

    def test_missing_file(self):
        r = self.cli(os.path.join(self.tmp.name, "nope.fprg"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot read", r.stderr)


if __name__ == "__main__":
    unittest.main()
