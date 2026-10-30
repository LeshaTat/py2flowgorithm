"""Tests for the py2fprg converter (run: python3 -m unittest tests.test_py2fprg -v)."""
import contextlib
import io
import os
import re
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fprg_run  # noqa: E402
from py2fprg import ConvertError, convert_path, convert_source  # noqa: E402

try:
    import fprg_lint  # noqa: E402
except ImportError:  # the linter is optional for these tests
    fprg_lint = None

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "examples", "arith_quiz")

ALLOWED = {
    "flowgorithm": {"fileversion"}, "attributes": set(), "attribute": {"name", "value"},
    "function": {"name", "type", "variable"}, "parameters": set(), "parameter": {"name", "type", "array"},
    "body": set(), "declare": {"name", "type", "array", "size"}, "assign": {"variable", "expression"},
    "input": {"variable"}, "output": {"expression", "newline"}, "if": {"expression"}, "then": set(),
    "else": set(), "while": {"expression"}, "do": {"expression"}, "call": {"expression"},
    "for": {"variable", "start", "end", "direction", "step"}, "comment": {"text"}, "breakpoint": set(),
}


def lint_ok(xml: str, name: str = "generated.fprg") -> None:
    """Every document the converter emits must pass fprg_lint without errors."""
    if fprg_lint is None:
        return
    findings = fprg_lint.lint_string(xml, name)
    errors = [f for f in findings if f.severity == "ERROR"]
    assert not errors, "\n".join(str(f) for f in errors) + "\n" + xml


def conv(code: str, **kw) -> str:
    kw.setdefault("metadata", False)
    xml = convert_source(textwrap.dedent(code), "prog", **kw)
    lint_ok(xml)
    return xml


def body_xml(code: str, **kw) -> str:
    """The inner XML of Main's body, indentation stripped, for compact assertions."""
    xml = conv(code, **kw)
    m = re.search(r"<function name=\"Main\".*?<body>(.*?)</body>", xml, re.S)
    assert m, xml
    return "\n".join(line.strip() for line in m.group(1).strip().splitlines())


def run_python(code: str, inputs=(), randoms=()) -> str:
    """Console output of a snippet run as a script (its main() is called), with scripted input()
    answers (prompts on their own line, like Output shapes) and random.randint values used the
    way the converter's `a + Random(b - a + 1)` uses Random()."""
    answers, rnd = iter(inputs), iter(randoms)

    def fake_input(prompt=""):
        if prompt:
            print(prompt)
        return next(answers)

    out = io.StringIO()
    ns = {"__name__": "prog"}
    with patch("builtins.input", side_effect=fake_input), \
            patch("random.randint", side_effect=lambda a, b: a + next(rnd) % (b - a + 1)), \
            contextlib.redirect_stdout(out):
        exec(compile(code, "prog.py", "exec"), ns)
        if "main" in ns:
            ns["main"]()
    return out.getvalue()


def same_as_python(test: unittest.TestCase, code: str, inputs=(), randoms=(), **kw) -> str:
    """Differential check: the flowchart (run by fprg_run) prints exactly what Python prints."""
    code = textwrap.dedent(code)
    warnings = kw.pop("warnings", [])
    xml = conv(code, warnings=warnings, **kw)
    expected = run_python(code, inputs, randoms)
    actual = fprg_run.run_string(xml, list(inputs), random_values=list(randoms))
    test.assertEqual(expected, actual, xml)
    return xml


def warnings_of(code: str) -> list[str]:
    warnings: list = []
    conv(code, warnings=warnings)
    return [w.msg for w in warnings]


def error_of(code: str, **kw) -> str:
    """The ConvertError message a snippet produces (fails if it converts)."""
    try:
        convert_source(textwrap.dedent(code), "prog", metadata=False, **kw)
    except ConvertError as e:
        return e.format()
    raise AssertionError("expected a ConvertError")


def check_schema(xml: str) -> None:
    root = ET.fromstring(xml)
    for el in root.iter():
        assert el.tag in ALLOWED, f"unknown element {el.tag}"
        extra = set(el.attrib) - ALLOWED[el.tag]
        assert not extra, f"unknown attributes {extra} on {el.tag}"


class SchemaTest(unittest.TestCase):
    def test_skeleton(self):
        xml = conv('''
            """Demo program.

            Second line of the docstring.
            """
            def main():
                print("hi")
        ''')
        check_schema(xml)
        self.assertTrue(xml.startswith('<?xml version="1.0"?>\n<flowgorithm fileversion="3.0">\n'))
        self.assertIn('<attribute name="name" value="Demo program"/>', xml)
        self.assertIn('name="about" value="Demo program.&#13;&#10;&#13;&#10;Second line of the docstring."', xml)
        self.assertIn('<function name="Main" type="None" variable="">\n        <parameters/>\n        <body>', xml)
        self.assertTrue(xml.endswith("</flowgorithm>\n"))

    def test_escaping(self):
        xml = conv('''
            def main():
                s = "x < y & \\"q\\" é"  # comment with <tag>
                print(s)
        ''')
        self.assertIn('expression="&quot;x &lt; y &amp; &quot; &amp; ToChar(34) &amp; &quot;q&quot; &amp; '
                      'ToChar(34) &amp; &quot; &#233;&quot;"', xml)
        self.assertIn('<comment text="comment with &lt;tag&gt;"/>', xml)

    def test_metadata_attributes(self):
        xml = convert_source("def main():\n    print(1)\n", "prog", author="me")
        self.assertIn('<attribute name="authors" value="me"/>', xml)
        for key in ("saved", "created", "edited"):
            self.assertRegex(xml, rf'<attribute name="{key}" value="[^"]+"/>')

    def test_fileversion_option(self):
        self.assertIn('fileversion="4.2"', conv("def main():\n    print(1)\n", fileversion="4.2"))


class DeclarationTest(unittest.TestCase):
    def test_hoisted_and_grouped_by_type(self):
        body = body_xml('''
            def main():
                n = 1
                x = 2.5
                name = "a"
                ok = True
                m = n + 1
        ''')
        self.assertEqual(body.splitlines()[:4], [
            '<declare name="n, m" type="Integer" array="False" size=""/>',
            '<declare name="x" type="Real" array="False" size=""/>',
            '<declare name="name" type="String" array="False" size=""/>',
            '<declare name="ok" type="Boolean" array="False" size=""/>',
        ])

    def test_int_then_float_widens_to_real(self):
        body = body_xml('''
            def main():
                x = 0
                x = x + 0.5
        ''')
        self.assertIn('<declare name="x" type="Real"', body)

    def test_annotations_win(self):
        body = body_xml('''
            def main():
                x: float = 0
                n: int
                n = 3
        ''')
        self.assertIn('<declare name="x" type="Real"', body)
        self.assertIn('<declare name="n" type="Integer"', body)

    def test_conflicting_types_error(self):
        with self.assertRaises(ConvertError) as cm:
            conv("def main():\n    x = 1\n    x = 'a'\n")
        self.assertIn("two types", str(cm.exception))

    def test_unknown_type_error(self):
        with self.assertRaises(ConvertError) as cm:
            conv("def main():\n    x = y\n")
        self.assertIn("not defined", str(cm.exception))


class InputOutputTest(unittest.TestCase):
    def test_input_forms(self):
        body = body_xml('''
            def main():
                name = input("Name?")
                age = int(input("Age?"))
                h = float(input())
                raw = str(input("Raw").strip())
        ''')
        self.assertIn('<output expression="&quot;Name?&quot;" newline="True"/>\n<input variable="name"/>', body)
        self.assertIn('<output expression="&quot;Age?&quot;" newline="True"/>\n<input variable="age"/>', body)
        self.assertIn('<declare name="age" type="Integer"', body)
        self.assertIn('<declare name="h" type="Real"', body)
        self.assertIn('<declare name="name, raw" type="String"', body)
        self.assertNotIn('newline="True"/>\n<input variable="h"', body)  # no prompt -> no output

    def test_print_variants(self):
        body = body_xml('''
            def main():
                n = 3
                print("a", n, "b")
                print("no newline", end="")
                print("x", "y", sep="-")
                print()
                print("two\\nlines")
                print(str(n) + " items")
                print(f"value={n:.2f}!")
        ''')
        self.assertIn('<output expression="&quot;a &quot; &amp; n &amp; &quot; b&quot;" newline="True"/>', body)
        self.assertIn('<output expression="&quot;no newline&quot;" newline="False"/>', body)
        self.assertIn('<output expression="&quot;x-y&quot;" newline="True"/>', body)
        self.assertIn('<output expression="&quot;&quot;" newline="True"/>', body)
        self.assertIn('<output expression="&quot;two&quot;" newline="True"/>\n<output expression="&quot;lines&quot;" newline="True"/>', body)
        self.assertIn('<output expression="n &amp; &quot; items&quot;" newline="True"/>', body)
        self.assertIn('<output expression="&quot;value=&quot; &amp; ToFixed(n, 2) &amp; &quot;!&quot;" newline="True"/>', body)

    def test_input_as_statement_pauses(self):
        body = body_xml('''
            def main():
                input("Press enter")
        ''')
        self.assertIn('<input variable="pause"/>', body)


class ControlFlowTest(unittest.TestCase):
    def test_if_elif_else(self):
        body = body_xml('''
            def main():
                n = int(input())
                if n > 0:
                    print("pos")
                elif n == 0:
                    print("zero")
                else:
                    print("neg")
        ''')
        self.assertIn('<if expression="n &gt; 0">\n<then>\n<output expression="&quot;pos&quot;" newline="True"/>\n</then>\n'
                      '<else>\n<if expression="n == 0">\n<then>', body)
        self.assertIn('<else>\n<output expression="&quot;neg&quot;" newline="True"/>\n</else>\n</if>\n</else>\n</if>', body)

    def test_if_without_else_has_empty_else(self):
        body = body_xml('''
            def main():
                n = 1
                if n:
                    print(1)
        ''')
        self.assertIn("</then>\n<else/>\n</if>", body)

    def test_while(self):
        body = body_xml('''
            def main():
                n = 10
                while n > 0:
                    n -= 1
        ''')
        self.assertIn('<while expression="n &gt; 0">\n<assign variable="n" expression="n - 1"/>\n</while>', body)

    def test_while_true_trailing_break_is_do_loop(self):
        body = body_xml('''
            def main():
                while True:
                    n = int(input("n"))
                    if n >= 0:
                        break
        ''')
        self.assertIn('<do expression="n &lt; 0">\n<output expression="&quot;n&quot;" newline="True"/>\n'
                      '<input variable="n"/>\n</do>', body)

    def test_while_true_leading_break_is_while(self):
        body = body_xml('''
            def main():
                n = 0
                while True:
                    if n > 5 or n == 3:
                        break
                    n += 1
        ''')
        self.assertIn('<while expression="not (n &gt; 5 or n == 3)">', body)

    def test_break_anywhere_stops_the_loop_with_a_flag(self):
        body = body_xml("def main():\n    n = 0\n    while n < 5:\n        n += 1\n        if n == 3:\n"
                        "            break\n    print(n)\n")
        self.assertIn('<assign variable="done" expression="false"/>\n<while expression="not done and n &lt; 5">', body)
        self.assertIn('<assign variable="done" expression="true"/>', body)

    def test_for_range_variants(self):
        body = body_xml('''
            def main():
                n = 5
                xs = [0] * n
                for i in range(n):
                    print(i)
                for i in range(1, 11):
                    print(i)
                for i in range(10, 0, -2):
                    print(i)
                for i in range(0, n + 1):
                    print(i)
                for i in range(len(xs)):
                    print(xs[i])
        ''')
        self.assertIn('<for variable="i" start="0" end="n - 1" direction="inc" step="1">', body)
        self.assertIn('<for variable="i" start="1" end="10" direction="inc" step="1">', body)
        self.assertIn('<for variable="i" start="10" end="1" direction="dec" step="2">', body)
        self.assertIn('<for variable="i" start="0" end="n" direction="inc" step="1">', body)
        self.assertIn('<for variable="i" start="0" end="Size(xs) - 1" direction="inc" step="1">', body)

    def test_for_each_over_array_string_enumerate(self):
        body = body_xml('''
            def main():
                xs = [1, 2, 3]
                s = "abc"
                for x in xs:
                    print(x)
                for ch in s:
                    print(ch)
                for i, v in enumerate(xs):
                    print(i, v)
        ''')
        self.assertIn('<for variable="xIndex" start="0" end="Size(xs) - 1" direction="inc" step="1">\n'
                      '<assign variable="x" expression="xs[xIndex]"/>', body)
        self.assertIn('<for variable="chIndex" start="0" end="Len(s) - 1" direction="inc" step="1">\n'
                      '<assign variable="ch" expression="Char(s, chIndex)"/>', body)
        self.assertIn('<for variable="i" start="0" end="Size(xs) - 1" direction="inc" step="1">\n'
                      '<assign variable="v" expression="xs[i]"/>', body)


class ArrayTest(unittest.TestCase):
    def test_creation_forms(self):
        body = body_xml('''
            def main():
                n = 4
                zeros = [0] * n
                ones = [1] * n
                names: list[str] = [""] * (n + 1)
                lit = [3, 4]
                lit[0] = 7
                print(len(lit), lit[-1])
        ''')
        self.assertIn('<declare name="zeros" type="Integer" array="True" size="n"/>', body)
        self.assertIn('<declare name="ones" type="Integer" array="True" size="n"/>\n'
                      '<for variable="idx" start="0" end="n - 1" direction="inc" step="1">\n'
                      '<assign variable="ones[idx]" expression="1"/>\n</for>', body)
        self.assertIn('<declare name="names" type="String" array="True" size="n + 1"/>', body)
        self.assertIn('<declare name="lit" type="Integer" array="True" size="2"/>\n'
                      '<assign variable="lit[0]" expression="3"/>\n<assign variable="lit[1]" expression="4"/>', body)
        self.assertIn('<assign variable="lit[0]" expression="7"/>', body)
        self.assertIn('<output expression="Size(lit) &amp; &quot; &quot; &amp; lit[Size(lit) - 1]" newline="True"/>', body)
        self.assertNotIn('name="zeros, ones', body)  # arrays are not hoisted

    def test_append_is_error(self):
        with self.assertRaises(ConvertError) as cm:
            conv("def main():\n    xs = [0] * 3\n    xs.append(1)\n")
        self.assertIn("method", str(cm.exception))


class ExpressionTest(unittest.TestCase):
    def expr(self, src: str, prelude: str = "a = 1\nb = 2\nc = 3\ns = 'x'\nxs = [0] * 3\n") -> str:
        code = "import math\nimport random\n\ndef main():\n" + textwrap.indent(prelude + f"r = {src}\n", "    ")
        xml = conv(code)
        m = re.search(r'<assign variable="r" expression="([^"]*)"/>', xml)
        assert m, xml
        return m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

    def test_arithmetic(self):
        self.assertEqual(self.expr("a + b * c"), "a + b * c")
        self.assertEqual(self.expr("(a + b) * c"), "(a + b) * c")
        self.assertEqual(self.expr("a - (b - c)"), "a - (b - c)")
        self.assertEqual(self.expr("a ** 2"), "a ^ 2")
        self.assertEqual(self.expr("-a ** 2"), "-(a ^ 2)")
        self.assertEqual(self.expr("a ** b ** c"), "a ^ (b ^ c)")
        self.assertEqual(self.expr("a // b"), "Int(a / b)")
        self.assertEqual(self.expr("a % b"), "a % b")
        self.assertEqual(self.expr("a / b"), "a / b")
        self.assertEqual(self.expr("-(-a)"), "-(-a)")

    def test_logic_and_comparison(self):
        self.assertEqual(self.expr("not a == b"), "a != b")
        self.assertEqual(self.expr("not (a == b and c == a)"), "not (a == b and c == a)")
        self.assertEqual(self.expr("a < b < c"), "a < b and b < c")
        self.assertEqual(self.expr("a == b or b != c and a <= c"), "a == b or b != c and a <= c")
        self.assertEqual(self.expr("(a == b or b != c) and a >= c"), "(a == b or b != c) and a >= c")
        self.assertEqual(self.expr("True"), "true")

    def test_strings(self):
        self.assertEqual(self.expr('s + "y"'), 's & "y"')
        self.assertEqual(self.expr('"n=" + str(a)'), '"n=" & a')
        self.assertEqual(self.expr('f"{a}-{s}"'), 'a & "-" & s')
        self.assertEqual(self.expr("s[0]"), "Char(s, 0)")
        self.assertEqual(self.expr("len(s)"), "Len(s)")
        self.assertEqual(self.expr("len(xs)"), "Size(xs)")
        self.assertEqual(self.expr("ord(s)"), "ToCode(s)")
        self.assertEqual(self.expr("chr(a)"), "ToChar(a)")
        self.assertEqual(self.expr("int(s)"), "ToInteger(s)")
        self.assertEqual(self.expr("float(s)"), "ToReal(s)")
        self.assertEqual(self.expr("str(a)"), "ToString(a)")
        self.assertEqual(self.expr('s == "a\\tb"'), 's == "a" & ToChar(9) & "b"'.replace('s == "a" & ToChar(9) & "b"', 's == "a" & ToChar(9) & "b"'))

    def test_math_and_random(self):
        self.assertEqual(self.expr("math.sqrt(a)"), "Sqrt(a)")
        self.assertEqual(self.expr("math.pi * a"), "pi * a")
        self.assertEqual(self.expr("abs(a - b)"), "Abs(a - b)")
        self.assertEqual(self.expr("round(a / b, 2)"), "ToReal(ToFixed(a / b, 2))")
        self.assertEqual(self.expr("random.randint(1, 6)"), "1 + Random(6)")
        self.assertEqual(self.expr("random.randint(0, a)"), "Random(a + 1)")
        self.assertEqual(self.expr("random.randrange(a)"), "Random(a)")
        self.assertEqual(self.expr("int(a / b)"), "Int(a / b)")
        self.assertEqual(self.expr("float(a)"), "a")

    def test_from_import(self):
        xml = conv("from math import sqrt, pi\n\ndef main():\n    r = sqrt(pi)\n")
        self.assertIn('expression="Sqrt(pi)"', xml)

    def test_unsupported(self):
        for src in ("[x for x in xs]", "a & b", "s.split()", "s.replace(s, s)", "s in s", "a in a", "s[::2]"):
            with self.assertRaises(ConvertError, msg=src):
                self.expr(src)


class FunctionTest(unittest.TestCase):
    def test_parameters_and_named_return_variable(self):
        xml = conv('''
            def total(xs: list[int], n: int) -> int:
                sum_ = 0
                for i in range(n):
                    sum_ += xs[i]
                return sum_

            def main():
                xs = [0] * 3
                print(total(xs, 3))
        ''')
        self.assertIn('<function name="total" type="Integer" variable="sum">', xml)
        self.assertIn('<parameter name="xs" type="Integer" array="True"/>\n            <parameter name="n" type="Integer" array="False"/>', xml)
        self.assertIn('<declare name="sum, i" type="Integer"', xml)
        self.assertIn('expression="total(xs, 3)"', xml)

    def test_result_variable_and_early_return(self):
        xml = conv('''
            def sign(x: float) -> int:
                if x > 0:
                    return 1
                if x < 0:
                    return -1
                return 0

            def main():
                print(sign(2.5))
        ''')
        self.assertIn('<function name="sign" type="Integer" variable="result">', xml)
        body = re.search(r'<function name="sign".*?<body>(.*?)</body>', xml, re.S).group(1)
        compact = "\n".join(l.strip() for l in body.strip().splitlines())
        self.assertEqual(compact, '\n'.join([
            '<declare name="result" type="Integer" array="False" size=""/>',
            '<if expression="x &gt; 0">', '<then>', '<assign variable="result" expression="1"/>', '</then>',
            '<else>', '<if expression="x &lt; 0">', '<then>', '<assign variable="result" expression="-1"/>', '</then>',
            '<else>', '<assign variable="result" expression="0"/>', '</else>', '</if>', '</else>', '</if>']))

    def test_return_type_inferred_and_void_call(self):
        xml = conv('''
            def half(x):
                return x / 2

            def greet(name: str):
                print("Hello " + name)

            def main():
                greet("Bob")
                print(half(4))
        ''')
        self.assertIn('<function name="half" type="Real" variable="result">', xml)
        self.assertIn('<parameter name="x" type="Integer"', xml)  # inferred from the literal call site
        self.assertIn('<call expression="greet(&quot;Bob&quot;)"/>', xml)

    def test_default_arguments_filled_in(self):
        xml = conv('''
            def power(base: int, exp: int = 2) -> int:
                return base ** exp

            def main():
                print(power(3), power(2, 5))
        ''')
        self.assertIn("power(3, 2)", xml)
        self.assertIn("power(2, 5)", xml)

    def test_recursion_needs_annotation(self):
        with self.assertRaises(ConvertError):
            conv('''
                def fact(n: int):
                    if n <= 1:
                        return 1
                    return n * fact(n - 1)

                def main():
                    print(fact(5))
            ''')
        xml = conv('''
            def fact(n: int) -> int:
                if n <= 1:
                    return 1
                return n * fact(n - 1)

            def main():
                print(fact(5))
        ''')
        self.assertIn('expression="n * fact(n - 1)"', xml)

    def test_return_in_loop_sets_the_result_and_leaves(self):
        xml = same_as_python(self, '''
            def find(xs: list[int], v: int) -> int:
                for i in range(len(xs)):
                    if xs[i] == v:
                        return i
                return -1

            def main():
                xs = [3, 1, 4]
                print(find(xs, 1), find(xs, 5))
        ''')
        self.assertIn('<while expression="not returned and iCounter &lt;= Size(xs) - 1">', xml)
        self.assertIn('<if expression="not returned">', xml)

    def test_tuple_swap_uses_temps(self):
        body = body_xml('''
            def main():
                a = 1
                b = 2
                a, b = b, a
                c, d = 3, 4
        ''')
        self.assertIn('<assign variable="temp" expression="b"/>\n<assign variable="temp2" expression="a"/>\n'
                      '<assign variable="a" expression="temp"/>\n<assign variable="b" expression="temp2"/>', body)
        self.assertIn('<assign variable="c" expression="3"/>\n<assign variable="d" expression="4"/>', body)

    def test_main_errors(self):
        with self.assertRaises(ConvertError):
            conv("def main():\n    return 1\n")
        with self.assertRaises(ConvertError):
            conv("def main():\n    print(1)\n\nprint(2)\n")
        with self.assertRaises(ConvertError):
            conv("def main():\n    global x\n    x = 1\n")
        with self.assertRaises(ConvertError):
            conv("class A:\n    pass\n\ndef main():\n    print(1)\n")

    def test_module_level_program(self):
        xml = conv('''
            n = 3
            print(n * 2)
        ''')
        self.assertIn('<assign variable="n" expression="3"/>\n            <output expression="n * 2"', xml)
        check_schema(xml)


class NamesConstantsCommentsTest(unittest.TestCase):
    def test_identifier_legalisation(self):
        body = body_xml('''
            def main():
                my_var = 1
                len = 2
                string = "s"
                N = 3
                n = 4
                print(my_var, len, string, N, n)
        ''')
        self.assertIn('<declare name="myVar, lenVal, N, n2" type="Integer"', body)
        self.assertIn('<declare name="stringVal" type="String"', body)

    def test_constants_copied_into_functions(self):
        xml = conv('''
            MAX_TRIES = 3
            GREETING = "hi"

            def tries_left(used: int) -> int:
                return MAX_TRIES - used

            def main():
                print(GREETING, tries_left(1))
        ''')
        self.assertIn('<declare name="result, maxTries" type="Integer"', xml)
        self.assertIn('<assign variable="maxTries" expression="3"/>', xml)
        self.assertIn('<assign variable="result" expression="maxTries - used"/>', xml)
        self.assertIn('<assign variable="GREETING" expression="&quot;hi&quot;"/>', xml)
        self.assertNotIn("maxTries", re.search(r'<function name="Main".*?</function>', xml, re.S).group(0))

    def test_comments_and_directives(self):
        body = body_xml('''
            def main():
                # leading comment
                n = 1  # trailing comment
                # fg: breakpoint
                n += 1
                print(n)  # fg: ignore
                # fg: ignore
                n = 99
                print(n)
                # closing comment
        ''')
        self.assertEqual(body.splitlines(), [
            '<declare name="n" type="Integer" array="False" size=""/>',
            '<comment text="leading comment"/>',
            '<comment text="trailing comment"/>',
            '<assign variable="n" expression="1"/>',
            '<breakpoint/>',
            '<assign variable="n" expression="n + 1"/>',
            '<output expression="n" newline="True"/>',
            '<comment text="closing comment"/>',
        ])

    def test_no_comments_option(self):
        body = body_xml('''
            def main():
                """Docstring."""
                # comment
                print(1)
        ''', comments=False)
        self.assertNotIn("<comment", body)

    def test_docstrings_and_directive_attributes(self):
        xml = conv('''
            # fg: name Guess Game
            # fg: author Someone
            # fg: about A guessing game.
            def helper(n: int) -> int:
                """Doubles n."""
                return n * 2

            def main():
                print(helper(2))
        ''')
        self.assertIn('<attribute name="name" value="Guess Game"/>', xml)
        self.assertIn('<attribute name="authors" value="Someone"/>', xml)
        self.assertIn('<attribute name="about" value="A guessing game."/>', xml)
        self.assertIn('<comment text="Doubles n."/>', xml)


class ProjectTest(unittest.TestCase):
    def make_project(self, files: dict) -> str:
        root = tempfile.mkdtemp(prefix="py2fprg_")
        for rel, content in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(textwrap.dedent(content))
        return root

    def test_multi_module_project(self):
        root = self.make_project({
            "app.py": '''
                """My App."""
                import helpers
                from helpers import LIMIT, double
                from util.text import shout

                def main():
                    n = int(input("n?"))
                    print(double(n), helpers.triple(n), shout("hi"), LIMIT)
                    helpers.unused_elsewhere(1)

                if __name__ == "__main__":
                    main()
            ''',
            "helpers.py": '''
                LIMIT = 10

                def double(n: int) -> int:
                    return n * 2

                def triple(n: int) -> int:
                    return n * 3

                def unused_elsewhere(n: int):
                    print(n)

                def never_called(n: int) -> int:
                    return n
            ''',
            "util/__init__.py": "",
            "util/text.py": '''
                def shout(s: str) -> str:
                    return s + "!"
            ''',
            "tests/test_helpers.py": "import helpers\nassert helpers.double(2) == 4\n",
            "test_app.py": "raise SystemExit('tests are never converted')\n",
        })
        outputs = convert_path(root, metadata=False)
        self.assertEqual(len(outputs), 1)
        out_path, xml = outputs[0]
        self.assertEqual(os.path.basename(out_path), "app.fprg")
        check_schema(xml)
        lint_ok(xml)
        names = re.findall(r'<function name="([^"]+)"', xml)
        self.assertEqual(names, ["Main", "double", "triple", "unusedElsewhere", "shout"])
        self.assertIn('<attribute name="name" value="My App"/>', xml)
        self.assertIn('<assign variable="LIMIT" expression="10"/>', xml)
        self.assertIn('<call expression="unusedElsewhere(1)"/>', xml)
        outputs = convert_path(root, metadata=False, all_functions=True)
        self.assertIn('<function name="neverCalled"', outputs[0][1])

    def test_name_clash_between_modules(self):
        root = self.make_project({
            "main.py": '''
                import a
                import b

                def main():
                    print(a.helper(1), b.helper(2))
            ''',
            "a.py": "def helper(n: int) -> int:\n    return n\n",
            "b.py": "def helper(n: int) -> int:\n    return n + 1\n",
        })
        warnings = []
        xml = convert_path(root, metadata=False, warnings=warnings)[0][1]
        self.assertIn('<function name="helper"', xml)
        self.assertIn('<function name="helper2"', xml)
        self.assertIn("helper(1)", xml)
        self.assertIn("helper2(2)", xml)
        self.assertTrue(any("renamed" in w.msg for w in warnings))

    def test_ignored_function_called_is_error(self):
        root = self.make_project({
            "main.py": '''
                # fg: ignore
                def helper(n: int) -> int:
                    return n

                def main():
                    print(helper(1))
            ''',
        })
        with self.assertRaises(ConvertError) as cm:
            convert_path(root)
        self.assertIn("fg: ignore", str(cm.exception))


class SampleProjectTest(unittest.TestCase):
    def test_sample_converts_and_is_valid(self):
        outputs = convert_path(SAMPLE, metadata=False)
        self.assertEqual(len(outputs), 1)
        out, xml = outputs[0]
        self.assertTrue(out.endswith("quiz.fprg"))
        check_schema(xml)
        names = re.findall(r'<function name="([^"]+)"', xml)
        self.assertEqual(names[0], "Main")
        self.assertIn("playRound", names)
        self.assertIn("askInt", names)
        self.assertNotIn("summaryString", names)  # fg: ignore
        self.assertIn('<do expression="not isYesOrNo(answer)">', xml)
        if fprg_lint is not None:
            findings = fprg_lint.lint_string(xml, "quiz.fprg")
            errors = [f for f in findings if f.severity.lower().startswith("err")]
            self.assertEqual(errors, [], "\n".join(f"{f.path}: {f.message}" for f in errors))



class ReviewRegressionTest(unittest.TestCase):
    """Bugs found by the independent review; each test pins the fixed behaviour."""

    def make_project(self, files: dict) -> str:
        return ProjectTest.make_project(self, files)

    def test_return_of_module_constant_uses_result_variable(self):
        xml = conv('''
            MAX_TRIES = 3

            def limit() -> int:
                return MAX_TRIES

            def main():
                print(limit())
        ''')
        self.assertIn('<function name="limit" type="Integer" variable="result">', xml)
        self.assertIn('<assign variable="maxTries" expression="3"/>', xml)
        self.assertIn('<assign variable="result" expression="maxTries"/>', xml)

    def test_unrelated_broken_module_does_not_abort(self):
        root = self.make_project({
            "prog.py": 'def main():\n    print("hi")\n\nif __name__ == "__main__":\n    main()\n',
            "other.py": "class Thing:\n    pass\n",
            "sub/deeper.py": "@decorated\ndef f(x=compute()):\n    pass\n",
        })
        warnings = []
        outputs = convert_path(root, metadata=False, warnings=warnings)
        self.assertEqual(len(outputs), 1)
        self.assertIn('<output expression="&quot;hi&quot;"', outputs[0][1])
        self.assertTrue(any("skipped other.py" in w.msg for w in warnings))
        # ...but importing the broken module is still an error
        root2 = self.make_project({
            "prog.py": 'import other\n\ndef main():\n    other.f()\n',
            "other.py": "class Thing:\n    pass\n\ndef f():\n    print(1)\n",
        })
        with self.assertRaises(ConvertError) as cm:
            convert_path(root2, metadata=False)
        self.assertIn("classes", str(cm.exception))

    def test_shared_function_converted_twice_is_not_duplicated(self):
        root = self.make_project({
            "a.py": 'from shared import show\n\ndef main():\n    show(1)\n\nif __name__ == "__main__":\n    main()\n',
            "b.py": 'from shared import show\n\ndef main():\n    show(2)\n\nif __name__ == "__main__":\n    main()\n',
            "shared.py": '''
                def show(x: int):
                    if x > 0:
                        return
                    print("non-positive:", x)
                    print("done")
            ''',
        })
        warnings = []
        outputs = convert_path(root, metadata=False, warnings=warnings)
        self.assertEqual([os.path.basename(p) for p, _ in outputs], ["a.fprg", "b.fprg"])
        for _, xml in outputs:
            self.assertEqual(xml.count("<output "), 2, xml)
        self.assertFalse(any("unreachable" in w.msg for w in warnings))

    def test_ignored_call_statement_is_not_in_call_graph(self):
        xml = conv('''
            # fg: ignore
            def debug_dump(xs):
                import json
                print(json.dumps(xs))

            def main():
                xs = [0] * 3
                debug_dump(xs)  # fg: ignore
                print(xs[0])
        ''')
        self.assertNotIn("debugDump", xml)
        self.assertIn('<output expression="xs[0]"', xml)

    def test_module_level_program_keeps_def_comments_out_of_main(self):
        xml = conv('''
            x = 1
            # helper for printing
            # fg: ignore
            def helper():
                import os
                print(os.getcwd())
                # trailing in helper
            print(x)
            print("second")
        ''')
        body = re.search(r'<function name="Main".*?<body>(.*?)</body>', xml, re.S).group(1)
        self.assertIn('<output expression="x"', body)
        self.assertIn('<output expression="&quot;second&quot;"', body)
        self.assertNotIn("helper", body)
        self.assertNotIn("<comment", body)

    def test_bare_fstring_converts_to_text(self):
        body = body_xml('''
            def main():
                n = 5
                s = f"{n}"
                t = f"{s}"
                print(s, t)
        ''')
        self.assertIn('<assign variable="s" expression="ToString(n)"/>', body)
        self.assertIn('<assign variable="t" expression="s"/>', body)

    def test_negated_variable_range_step_is_descending(self):
        body = body_xml('''
            def main():
                n = 10
                k = 2
                for i in range(n, 0, -k):
                    print(i)
        ''')
        self.assertIn('<for variable="i" start="n" end="1" direction="dec" step="k">', body)

    def test_comments_follow_moved_statements(self):
        xml = conv('''
            def sign(x: int) -> int:
                if x > 0:
                    return 1
                # negative or zero
                y = -1
                return y

            def main():
                print(sign(2))
        ''')
        body = re.search(r'<function name="sign".*?<body>(.*?)</body>', xml, re.S).group(1)
        compact = "\n".join(l.strip() for l in body.strip().splitlines())
        self.assertIn('<else>\n<comment text="negative or zero"/>\n<assign variable="y" expression="-1"/>', compact)
        self.assertNotIn('expression="1"/>\n<comment', compact)

    def test_comment_after_elif_chain_stays_outside(self):
        body = body_xml('''
            def main():
                a = 1
                if a == 1:
                    print("one")
                elif a == 2:
                    print("two")
                else:  # note on else
                    print("many")
                # after if
                print("end")
        ''')
        self.assertIn('</if>\n</else>\n</if>\n<comment text="after if"/>\n<output expression="&quot;end&quot;"', body)
        self.assertIn('<else>\n<comment text="note on else"/>\n<output expression="&quot;many&quot;"', body)

    def test_truthiness_in_conditions(self):
        body = body_xml('''
            def main():
                n = 3
                s = "x"
                xs = [0] * 2
                ok = True
                while n:
                    n -= 1
                if s:
                    print(1)
                if not xs:
                    print(2)
                if n and s or ok:
                    print(3)
                while True:
                    n += 1
                    if n:
                        break
        ''')
        self.assertIn('<while expression="n != 0">', body)
        self.assertIn('<if expression="s != &quot;&quot;">', body)
        self.assertIn('<if expression="Size(xs) == 0">', body)
        self.assertIn('<if expression="n != 0 and s != &quot;&quot; or ok">', body)
        self.assertIn('<do expression="n == 0">', body)

    def test_non_boolean_value_logic_and_array_output_are_errors(self):
        with self.assertRaises(ConvertError):
            conv("def main():\n    a = 1\n    b = 2\n    c = a or b\n")
        with self.assertRaises(ConvertError):
            conv("def main():\n    xs = [0] * 2\n    print(xs)\n")

    def test_minor_review_items(self):
        self.assertIn('<declare name="k" type="Real"', conv("def main():\n    k = 2 ** -1\n    print(k)\n"))
        with self.assertRaises(ConvertError):
            conv("def main():\n    main()\n")
        with self.assertRaises(ConvertError):
            conv("COUNT = 0\nCOUNT = COUNT + 5\n\ndef main():\n    print(COUNT)\n")


class BugHuntRegressionTest(unittest.TestCase):
    """Findings of the adversarial bug hunt (docs/bug-hunt-findings.md, ids C0..C32 / leads L1..)."""

    # ---- expressions -------------------------------------------------------------------------
    def test_chained_comparison_with_a_call_in_the_middle(self):  # C0
        xml = same_as_python(self, '''
            import random

            def roll() -> int:
                print("rolling")
                return 4

            def main():
                if 1 <= random.randint(1, 10) <= 5:
                    print("low")
                if 2 < roll() < 6:
                    print("mid")
        ''', randoms=[3])
        self.assertIn('<assign variable="value" expression="1 + Random(10)"/>', xml)
        self.assertIn('<if expression="1 &lt;= value and value &lt;= 5">', xml)
        body = body_xml("def main():\n    x = 3\n    if 1 <= x <= 5:\n        print(x)\n")
        self.assertIn('<if expression="1 &lt;= x and x &lt;= 5">', body)

    def test_floor_division_and_modulo_follow_python(self):  # C1, C2
        xml = same_as_python(self, '''
            def shift(ch: str, k: int) -> str:
                code = ord(ch) - ord("a")
                return chr((code - k) % 26 + ord("a"))

            def main():
                n = -7
                print(n // 2, -n // 2, n % 2, 7 // -2, -7 % 3)
                i = 0
                print((i - 1) % 5)
                out = ""
                for ch in "cde":
                    out = out + shift(ch, 3)
                print(out)
                for a in [7, -7, 6, -6, 0]:
                    for b in [2, -2, 3, -3]:
                        d = a - 0
                        print(a, b, d // b, d % b)
        ''')
        self.assertIn('<if expression="remainder &lt; 0">', xml)  # the divisor's sign, fixed before use
        body = body_xml("def main():\n    t = 0\n    for i in range(10):\n        if i % 2 == 0:\n"
                        "            t += i // 2\n    print(t)\n")
        self.assertIn('<assign variable="t" expression="t + Int(i / 2)"/>', body)  # non-negative: plain
        self.assertNotIn("quotient", body)
        msgs = warnings_of("def main():\n    n = int(input())\n    print(n // 2)\n")
        self.assertTrue(any("sign is unknown" in m for m in msgs), msgs)

    def test_floor_ceil_and_round_follow_python(self):
        xml = same_as_python(self, '''
            import math

            def main():
                for x in [2.5, 3.5, -2.5, -3.5, 2.6, -2.6, 2.4, -2.4, 0.5, -0.5]:
                    print(x, math.floor(x), math.ceil(x), round(x))
                print(round(5), math.floor(9))
        ''')
        self.assertIn('<assign variable="rounded" expression="Int(x)"/>', xml)

    def test_negative_computed_index_counts_from_the_end_only_when_negative(self):
        same_as_python(self, '''
            def main():
                xs = [10, 20, 30, 40]
                for i in range(0, 3):
                    print(xs[-i])
                s = "flow"
                k = 2
                print(s[-k])
        ''')

    def test_very_long_expressions(self):
        code = "def main():\n    x = 1\n    y = " + " + ".join(["x"] * 800) + "\n    print(y)\n"
        self.assertEqual(fprg_run.run_string(conv(code)), "800\n")

    def test_list_methods_and_copies(self):
        same_as_python(self, '''
            def show(xs: list[int]):
                line = ""
                for x in xs:
                    line = line + str(x) + " "
                print(line)

            def main():
                xs = [5, 3, 8, 3, 1]
                print(xs.index(3), xs.count(3), xs.index(1))
                ys = sorted(xs)
                zs = sorted(xs, reverse=True)
                show(ys)
                show(zs)
                xs.sort()
                xs.reverse()
                show(xs)
                cs = xs.copy()
                cs[0] = 99
                show(cs)
                show(xs)
                names = ["bob", "Al", "cy", "al"]
                names.sort()
                for n in names:
                    print(n)
        ''')
        self.assertIn("arrays have a fixed size", error_of("def main():\n    xs = [1]\n    xs.append(2)\n"))

    def test_numbers_that_python_writes_with_an_exponent(self):  # C3
        cases = {"1e-05": "0.00001", "1.602176634e-19": "1.602176634 * 10 ^ -19",
                 "6.02214076e23": "6.02214076 * 10.0 ^ 23", "1e-8": "10 ^ -8",
                 "5e-324": "5 * 10 ^ -300 * 10 ^ -24", "1e16": "10000000000000000.0"}
        for literal, text in cases.items():
            with self.subTest(literal=literal):
                body = body_xml(f"def main():\n    x = {literal}\n    print(x)\n")
                self.assertIn(f'<assign variable="x" expression="{text}"/>', body)
                value = fprg_run.evaluate(text)
                self.assertAlmostEqual(value / float(literal), 1.0, places=14)
        xml = conv("CHARGE = -1.602176634e-19\n\ndef main():\n    print(CHARGE * 2)\n")
        self.assertIn('<assign variable="CHARGE" expression="-1.602176634 * 10 ^ -19"/>', xml)
        self.assertIn('expression="-(10.0 ^ 30)"', conv("BIG = -1e30\n\ndef main():\n    print(BIG)\n"))
        self.assertIn('expression="2 / (5 * 10 ^ -20)"', conv("def main():\n    print(2 / 5e-20)\n"))

    def test_randint_lower_bound_with_a_call(self):  # C4
        xml = same_as_python(self, '''
            import random

            def low() -> int:
                print("asking")
                return 3

            def main():
                r = random.randint(low(), 10)
                print(r)
        ''', randoms=[5])
        self.assertIn('<assign variable="r" expression="low2 + Random(10 - low2 + 1)"/>', xml)  # low() is taken

    def test_boolean_used_as_a_number(self):  # C5, C9
        xml = same_as_python(self, '''
            def main():
                xs = [3, -1, 4, -5, 9]
                positives = 0
                for x in xs:
                    positives += x > 0
                a = 3
                score = 0
                score = score + (a == 3)
                n = int(a > 2) * 10
                print(positives, score, n)
        ''')
        self.assertIn('<if expression="x &gt; 0">\n                    <then>\n'
                      '                        <assign variable="positives" expression="positives + 1"/>', xml)
        self.assertIn('<assign variable="score" expression="score + asNumber"/>', xml)

    def test_input_inside_expressions(self):
        same_as_python(self, '''
            def ask(prompt: str) -> int:
                return int(input(prompt))

            def show(n: int):
                print("got", n)

            def main():
                print("Hello, " + input("Name? ") + "!")
                total = 0
                total += int(input("Number: "))
                total += int(input("Number: "))
                print(total, f"{input('Unit? ')}s")
                if input("Continue? ") == "y":
                    print("yes")
                for i in range(int(input("How many? "))):
                    print(i)
                show(ask("n? ") * 2)
                x = int(input("x? "))
                if x > 0:
                    print("pos")
                elif input("zero? ") == "y":
                    print("zero")
        ''', ["Ann", "3", "4", "metre", "y", "2", "5", "0", "y"])

    def test_input_in_loop_conditions_is_read_before_every_test(self):
        xml = same_as_python(self, '''
            def main():
                count = 0
                while input("More? ") == "y":
                    count += 1
                n = 0
                while True:
                    n += 1
                    if input("Again? ") != "y":
                        break
                m = 0
                while True:
                    if int(input("Value? ")) < 0:
                        break
                    m += 1
                print(count, n, m)
        ''', ["y", "y", "n", "y", "n", "5", "-1"])
        body = re.search(r'<function name="Main".*?<body>(.*?)</body>', xml, re.S).group(1)
        self.assertEqual(body.count('<output expression="&quot;More? &quot;"'), 2)  # before + end of body
        self.assertEqual(body.count('<output expression="&quot;Again? &quot;"'), 1)  # end of the Do body

    def test_input_on_the_right_of_and_or_runs_only_when_python_runs_it(self):
        code = '''
            def main():
                x = int(input("x? "))
                if x > 0 and input("sure? ") == "y":
                    print("ok")
                if x < 0 or input("again? ") == "y":
                    print("again")
                n = 0
                while n < 3 and input("go? ") == "y":
                    n += 1
                print(n)
        '''
        same_as_python(self, code, ["1", "y", "n", "y", "y", "n"])
        xml = same_as_python(self, code, ["-1", "y", "n"])
        self.assertIn('<assign variable="test" expression="x &gt; 0"/>', xml)

    def test_calls_keep_pythons_order_of_evaluation(self):
        xml = same_as_python(self, '''
            import random

            def f() -> int:
                print("f")
                return 1

            def main():
                x = f() + int(input("n? "))
                if random.randint(1, 6) == int(input("Guess: ")):
                    print("right")
                print(x)
        ''', ["2", "4"], [3])
        self.assertIn('<assign variable="fResult" expression="f()"/>', xml)
        self.assertIn('<assign variable="draw" expression="1 + Random(6)"/>', xml)

    def test_values_python_evaluates_once(self):  # augmented element with a call in the index, list fill
        xml = same_as_python(self, '''
            import random

            def main():
                tally = [0] * 7
                for k in range(4):
                    tally[random.randint(1, 6)] += 1
                xs = [random.randint(1, 6)] * 3
                print(tally[1], tally[2], tally[3], xs[0], xs[1], xs[2])
        ''', randoms=[0, 1, 1, 2, 4])
        self.assertIn('<assign variable="tally[pos]" expression="tally[pos] + 1"/>', xml)
        self.assertIn('<assign variable="xs[idx]" expression="fill"/>', xml)

    def test_break_continue_and_return_inside_loops(self):
        same_as_python(self, '''
            def find(xs: list[int], target: int) -> int:
                for i in range(len(xs)):
                    if xs[i] == target:
                        return i
                return -1

            def has_pair(xs: list[int], target: int) -> bool:
                for i in range(len(xs)):
                    for j in range(i + 1, len(xs)):
                        if xs[i] + xs[j] == target:
                            return True
                    print("checked", i)
                return False

            def countdown(n: int):
                while n > 0:
                    if n == 2:
                        print("stop")
                        return
                    print(n)
                    n -= 1
                print("liftoff")

            def main():
                xs = [4, 8, 15, 16]
                print(find(xs, 15), find(xs, 3), "yes" if has_pair(xs, 12) else "no",
                      "yes" if has_pair(xs, 99) else "no")
                countdown(4)
                countdown(1)
                total = 0
                for x in xs:
                    if x > 10:
                        print("big", x)
                        break
                    total += x
                else:
                    print("no big one")
                for i in range(10):
                    if i % 2 == 0:
                        continue
                    total += i
                for i in range(len(xs)):
                    if xs[i] % 2 == 1:
                        break
                print(total, "stopped at", i)
                n = 10
                for k in range(n, 0, -2):
                    n = 0
                    if k < 5:
                        break
                    print(k)
        ''')

    def test_loop_and_a_half_becomes_a_priming_read(self):
        xml = same_as_python(self, '''
            def main():
                count = 0
                while True:
                    cmd = input("> ")
                    if cmd == "quit":
                        break
                    count += 1
                for attempt in range(3):
                    guess = int(input("guess? "))
                    if guess == 7:
                        print("right after", attempt + 1)
                        break
                    print("wrong")
                else:
                    print("out of tries")
                print(count)
        ''', ["a", "b", "quit", "1", "2", "3"])
        body = re.search(r'<function name="Main".*?<body>(.*?)</body>', xml, re.S).group(1)
        self.assertEqual(body.count('<input variable="cmd"/>'), 2)  # before the loop and at its end
        self.assertIn('<while expression="cmd != &quot;quit&quot;">', body)
        self.assertIn('<if expression="not done">', body)  # the for loop's else

    def test_conditional_expressions_min_max_sum_and_in(self):
        same_as_python(self, '''
            def sign(n: int) -> str:
                return "neg" if n < 0 else "pos"

            def main():
                x = int(input("x? "))
                label = "big" if x > 10 else "small"
                print(label, sign(x), "even" if x % 2 == 0 else "odd")
                y = int(input("y? ")) if x > 0 else 0
                xs = [4, 8, 1, 6]
                print(min(x, y), max(x, y, 3), min(xs), max(xs), sum(xs), sum(xs, 10))
                vowels = 0
                for ch in "programming":
                    if ch in "aeiou":
                        vowels += 1
                print(vowels, int(x in (1, 12, 13)), int(y in xs), int(x in range(1, 11)), int(y not in range(5)))
        ''', ["12", "6"])
        body = body_xml("def main():\n    x = 3\n    y = 1 if x > 2 else 2\n    print(y)\n")
        self.assertIn('<if expression="x &gt; 2">\n<then>\n<assign variable="y" expression="1"/>', body)
        self.assertIn("one character", error_of('def main():\n    s = input()\n    print(s in "hello")\n'))

    def test_string_methods_slices_and_repetition(self):
        same_as_python(self, '''
            def is_palindrome(word: str) -> bool:
                w = word.lower()
                return w == w[::-1]

            def main():
                n = int(input("rows? "))
                for i in range(1, n + 1):
                    print(" " * (n - i) + "*" * (2 * i - 1))
                if input("Again? ").lower() == "y":
                    print("yes")
                name = input("Name? ")
                print(name.upper(), "[" + name.strip() + "]", "[" + name.lstrip() + "]", "[" + name.rstrip() + "]")
                for w in ["123", "12a", "", "abc", "ABC", "aBc"]:
                    print(int(w.isdigit()), int(w.isalpha()), int(w.isupper()), int(w.islower()), w.count("a"))
                s = "flowchart"
                k = int(input("k? "))
                print(s[1:], s[:4], s[2:5], s[-3:], s[:-2], s[5:100], "[" + s[3:1] + "]", s[k:], s[-k:])
                for w in ["Level", "Python"]:
                    print(w, "yes" if is_palindrome(w) else "no")
        ''', ["3", "Y", "  Ada  ", "-2"])
        msgs = warnings_of("def main():\n    k = 2\n    s = 'ab'\n    print(s[1:], k)\n")
        self.assertFalse(any("renamed" in m for m in msgs), msgs)  # helper variables keep out of the way

    def test_loops_over_literals(self):
        same_as_python(self, '''
            def main():
                for ch in "hey":
                    print(ch)
                for x in [3, 1, 2]:
                    print(x * 2)
                for i, w in enumerate(("a", "b")):
                    print(i, w)
        ''')

    def test_fstring_repr_of_numbers(self):  # L4, L22
        same_as_python(self, 'def main():\n    n = 3\n    x = 2.5\n    print(f"{n=} {x!r}")\n')
        self.assertIn("only supported for numbers", error_of('def main():\n    s = "a"\n    print(f"{s!r}")\n'))

    # ---- for loops ---------------------------------------------------------------------------
    def test_nested_loops_reusing_a_counter_get_their_own(self):  # C12 and variants, L24, L25, L26
        cases = [
            "for _ in range(3):\n        for _ in range(2):\n            print('x')",
            "for i in range(3):\n        for i in range(2):\n            print(i)",
            "for k, x in enumerate(xs):\n        for k, y in enumerate(ys):\n            print(k, x, y)",
            "for x in range(3):\n        for x in xs:\n            print(x)",
            "for i in range(2):\n        for i, x in enumerate(xs):\n            print(i, x)",
            "for i, x in enumerate(xs):\n        for i in range(2):\n            print(i, x)",
            "for i in range(2):\n        for j in range(2):\n            for i in range(2):\n                print(i, j)",
            "for i in range(3):\n        for i in range(2):\n            pass\n        print(i)",
        ]
        for loops in cases:
            with self.subTest(loops=loops):
                warnings: list = []
                same_as_python(self, f"def main():\n    xs = [5, 6]\n    ys = [7, 8]\n    {loops}\n",
                               warnings=warnings)
                self.assertEqual([w.msg for w in warnings], [])
        body = body_xml("def main():\n    for _ in range(3):\n        for _ in range(2):\n            print(1)\n")
        self.assertIn('<for variable="vCounter" start="0" end="2"', body)
        self.assertIn('<for variable="v" start="0" end="1"', body)

    def test_loop_variable_changed_in_the_body_or_read_after_the_loop(self):  # C13, C16, L23, L27
        for stmt in ("j += 1", "j = 10", "j, k = j * 2, 2"):
            with self.subTest(stmt=stmt):
                same_as_python(self, f"def main():\n    for j in range(5):\n        {stmt}\n        print(j)\n"
                                     f"    print(j)\n")
        same_as_python(self, "def main():\n    xs = [1, 2]\n    for i, x in enumerate(xs):\n        i += 1\n"
                             "        print(i, x)\n")
        xml = same_as_python(self, "def main():\n    n = int(input('n'))\n    for i in range(n):\n        print(i)\n"
                                   "    print('last', i)\n", ["3"])
        self.assertIn('<for variable="iCounter" start="0" end="n - 1"', xml)
        self.assertIn('<assign variable="i" expression="iCounter"/>', xml)
        # a loop whose variable is not read afterwards still counts with it directly
        body = body_xml("def main():\n    for i in range(3):\n        print(i)\n    for i in range(2):\n"
                        "        print(i)\n")
        self.assertEqual(body.count('<for variable="i"'), 2)
        # the element variable of a for-each loop is not the counter: Python and Flowgorithm agree
        same_as_python(self, "def main():\n    xs = [1, 2]\n    for x in xs:\n        x = x * 10\n        print(x)\n")

    def test_negative_step_from_a_constant(self):  # C14
        warnings: list = []
        xml = same_as_python(self, '''
            STEP = -1
            POS = 2

            def main():
                n = int(input("n"))
                k = int(input("k"))
                for i in range(n, 0, -k):
                    print(i)
                for i in range(n, 0, STEP):
                    print(i)
                for i in range(0, n, POS):
                    print(i)
        ''', ["5", "2"], warnings=warnings)
        self.assertIn('<for variable="i" start="n" end="1" direction="dec" step="-STEP">', xml)
        self.assertFalse(any("assumed positive" in w.msg for w in warnings))

    def test_negated_break_condition_is_type_checked(self):  # C15
        self.assertIn("comparing String with Integer", error_of('''
            def main():
                while True:
                    s = input("word")
                    if s == 5:
                        break
        '''))

    def test_loop_variable_also_used_as_real(self):  # L18
        xml = same_as_python(self, '''
            def main():
                for x in range(3):
                    print(x)
                ys = [0.5, 1.5]
                for x in ys:
                    print(x)
        ''')
        self.assertIn('<for variable="xCounter"', xml)

    # ---- functions and returns -----------------------------------------------------------------
    def test_nested_and_elif_returns(self):  # C17, C18
        same_as_python(self, '''
            def is_valid(age: int, has_id: bool) -> str:
                if age >= 18:
                    if has_id:
                        return "yes"
                return "no"

            def classify(n: int) -> str:
                if n > 0:
                    if n % 2 == 0:
                        return "positive even"
                    print("odd")
                return "other"

            def f(n: int) -> int:
                if n > 10:
                    print("big")
                elif n > 5:
                    return 5
                print("tail")
                return 0

            def both(a: int, b: int):
                if a > 0:
                    if b > 0:
                        print("both")
                        return
                print("tail")

            def main():
                print(is_valid(20, True), is_valid(20, False), is_valid(10, True))
                print(classify(4), classify(3), classify(-1))
                print(f(7), f(11), f(1))
                both(1, 1)
                both(1, 0)
        ''')

    def test_return_none_is_a_bare_return(self):  # C23
        for ann in (" -> None", ""):
            with self.subTest(annotation=ann):
                same_as_python(self, f'''
                    def greet(name: str){ann}:
                        if name == "":
                            return None
                        print("Hello " + name)

                    def main():
                        greet("Bob")
                        greet("")
                ''')

    def test_real_returned_from_int_function_is_error(self):  # L28
        self.assertIn("annotated `-> int` but returns float",
                      error_of("def f() -> int:\n    return 2.5\n\ndef main():\n    print(f())\n"))

    def test_generators_and_starred_arguments_have_clear_errors(self):  # L16, L17
        self.assertIn("generators (yield)", error_of("def g():\n    yield 1\n\ndef main():\n    g()\n"))
        self.assertIn("*args in calls", error_of('''
            def add(a: int, b: int) -> int:
                return a + b
            def main():
                xs = [1, 2]
                print(add(*xs))
        '''))

    def test_import_inside_a_function(self):  # L11
        body = body_xml("def main():\n    import math\n    print(math.sqrt(2))\n")
        self.assertIn('<output expression="Sqrt(2)"', body)

    def test_local_variable_may_shadow_a_module_constant(self):  # L14, L15
        same_as_python(self, '''
            LIMIT = 10
            N = 3

            def f() -> int:
                LIMIT = 5
                return LIMIT * 2

            def main():
                for N in range(2):
                    print(N)
                print(f(), LIMIT)
        ''')
        self.assertIn("not defined before use",
                      error_of("LIMIT = 10\n\ndef f() -> int:\n    x = LIMIT\n    LIMIT = 5\n    return x\n\n"
                               "def main():\n    print(f())\n"))

    # ---- type inference ------------------------------------------------------------------------
    def test_variable_copied_before_its_source_widens_is_real(self):  # C6
        xml = conv('''
            def main():
                balance = 1000
                for year in range(3):
                    old = balance
                    balance = balance * 1.05
                    print(old, balance)
        ''')
        self.assertIn('<declare name="balance, old" type="Real"', xml)
        same_as_python(self, '''
            def main():
                k = 10
                while True:
                    last = k
                    k = k / 4
                    if k < 1:
                        break
                print(last)
        ''')
        xml = conv('''
            def f(n: int):
                total = 0
                for i in range(n):
                    half = total
                    total = total + 0.5
                return half

            def main():
                print(f(4))
        ''')
        self.assertIn('<function name="f" type="Real" variable="half">', xml)
        body = body_xml("def main():\n    x = 3\n    y = int(x)\n    x = x / 2\n    print(y, x)\n")
        self.assertIn('<assign variable="y" expression="Int(x)"/>', body)

    def test_annotated_int_does_not_take_a_real(self):  # C7, C10, C19
        cases = {
            "def half(n: int) -> float:\n    n = n / 2\n    return n\n": "parameter 'n' is annotated int",
            "def add(t: int, x: float) -> float:\n    t += x\n    return t\n": "parameter 't' is annotated int",
            "def g():\n    x: int = 2.5\n": "'x' is annotated int but assigned float",
            "def g():\n    x: int = 0\n    x = x + 0.5\n": "'x' is annotated int but is assigned float",
            "def g():\n    xs: list[int] = [0.5] * 3\n": "annotated list[int] but its elements are float",
            "def g():\n    xs: list[int] = [0] * 3\n    xs[0] = 0.5\n": "cannot store a float in 'xs', a list[int]",
            "def g() -> int:\n    t = 0\n    t = t + 0.5\n    return t\n": "returned by g(), annotated `-> int`",
        }
        for code, msg in cases.items():
            with self.subTest(code=code):
                self.assertIn(msg, error_of(code + "\n\ndef main():\n    pass\n", all_functions=True))

    def test_inferred_parameter_widens_with_its_body(self):  # C7 (un-annotated)
        xml = same_as_python(self, "def half(n=4):\n    n = n / 2\n    return n\n\ndef main():\n    print(half(5))\n")
        self.assertIn('<parameter name="n" type="Real" array="False"/>', xml)

    def test_real_stored_in_an_inferred_int_array_widens_it(self):  # C8
        xml = same_as_python(self, '''
            def main():
                n = 4
                xs = [0] * n
                for i in range(n):
                    xs[i] = i / 2
                print(xs[1], xs[3])
        ''')
        self.assertIn('<declare name="xs" type="Real" array="True" size="n"/>', xml)

    def test_parameter_types_join_all_call_sites_and_the_default(self):  # C20, C21
        xml = conv("def twice(x):\n    return x * 2\n\ndef main():\n    print(twice(1))\n    print(twice(2.5))\n")
        self.assertIn('<parameter name="x" type="Real" array="False"/>', xml)
        xml = conv('''
            def scale(x: float, factor=2) -> float:
                return x * factor

            def main():
                print(scale(3.0, 2.5))
                print(scale(3.0))
        ''')
        self.assertIn('<parameter name="factor" type="Real" array="False"/>', xml)

    def test_parameter_inference_ignores_ignored_code_and_reports_conflicts(self):  # C22
        xml = conv('''
            # fg: ignore
            def debug_show():
                show("debug")

            def show(x):
                print(x)

            def main():
                show(1)
        ''')
        self.assertIn('<parameter name="x" type="Integer" array="False"/>', xml)
        self.assertIn("passed values of different types",
                      error_of("def show(x):\n    print(x)\n\ndef main():\n    show(1)\n    show('a')\n"))

    def test_real_argument_for_an_int_parameter_is_error(self):
        self.assertIn("parameter 'n' of show() is int but gets float", error_of('''
            def show(n: int):
                print(n)

            def main():
                x = 2.5
                show(x)
        '''))

    # ---- `# fg: ignore` and comments -----------------------------------------------------------
    def test_ignore_removes_only_the_marked_statement(self):  # C25, C27, C28, C31
        body = body_xml('''
            x = 5
            # fg: ignore
            print("debug: x is", x)
            print(x * 2)
        ''')
        self.assertNotIn("debug", body)
        self.assertIn('<output expression="x * 2"', body)
        body = body_xml('# fg: ignore\ndef helper():\n    pass\n\nx = 5\nprint(x)\n')
        self.assertIn('<assign variable="x" expression="5"/>', body)
        body = body_xml('# fg: ignore\nclass Helper:\n    pass\n\nprint("hi")\nprint("there")\n')
        self.assertEqual(body.count("<output "), 2)
        body = body_xml('''
            def main():
                x = int(input("x?"))
                if x > 0:
                    print("pos")
                elif x == 0:  # fg: ignore
                    print("zero (debug)")
                else:
                    print("neg")
        ''')
        self.assertNotIn("zero", body)
        self.assertIn("neg", body)
        body = body_xml('''
            def main():
                a = 1
                if (a > 0
                        and a < 5):  # fg: ignore
                    print("debug")
                print("done")
        ''')
        self.assertNotIn("<if", body)
        # structural checks only see what is left after `# fg: ignore`
        xml = conv('''
            def g():
                # fg: ignore
                def inner():
                    return 1
                print(2)

            def main():
                x = 0
                while True:
                    x += 1
                    if x > 3:
                        break
                    print("debug", x)  # fg: ignore
                for i in range(3):
                    if i == 2:
                        return  # fg: ignore
                    print(i)
                g()
        ''')
        self.assertIn('<do expression="x &lt;= 3">', xml)
        self.assertIn('<if expression="i == 2">\n                    <then/>', xml)
        self.assertIn('<function name="g" type="None" variable="">', xml)

    def test_ignore_on_first_body_statement_and_on_else(self):
        body = body_xml('''
            def main():
                a = 1
                if a > 0:
                    # fg: ignore
                    print("debug")
                    print("kept")
                else:  # fg: ignore
                    print("debug else")
                print("end")
        ''')
        self.assertIn('<then>\n<output expression="&quot;kept&quot;"', body)
        self.assertIn("<else/>", body)
        self.assertNotIn("debug", body)

    def test_orphan_and_misspelled_directives_warn(self):  # L29, L30
        warnings: list = []
        same_as_python(self, '''
            def main():
                a = True
                if a:
                    x = 1
                    # fg: ignore
                print("after")
        ''', warnings=warnings)
        self.assertTrue(any("not followed by a statement" in w.msg for w in warnings))
        msgs = warnings_of("# fg: ignroe\ndef helper():\n    print(1)\n\ndef main():\n    print(2)\n")
        self.assertTrue(any("unknown directive 'fg: ignroe'" in m for m in msgs), msgs)

    def test_ignored_main_and_decorated_ignored_function(self):  # C26, C29
        self.assertIn("marked `fg: ignore`", error_of('# fg: ignore\ndef main():\n    print("hi")\n'))
        xml = conv('''
            import functools

            @functools.lru_cache(maxsize=None)
            def cached(n: int) -> int:  # fg: ignore
                return n * 2

            def main():
                print(1)
        ''')
        self.assertNotIn("cached", xml)

    def test_ignored_function_may_use_any_python(self):  # L12
        xml = conv('# fg: ignore\ndef helper(*args, **kw) -> "dict[str, int]":\n    return {}\n\n'
                   'def main():\n    print(1)\n')
        self.assertNotIn("helper", xml)

    def test_comment_placement(self):  # C24, C30, C32
        xml = conv('''
            def f(n: int) -> int:
                if n > 0:
                    print("pos")
                else:
                    # negative case
                    return -1
                print("after")
                return 1

            def main():
                print(f(3))
        ''')
        body = re.search(r'<function name="f".*?<body>(.*?)</body>', xml, re.S).group(1)
        compact = "\n".join(line.strip() for line in body.strip().splitlines())
        self.assertIn('<else>\n<comment text="negative case"/>\n<assign variable="result" expression="-1"/>', compact)
        body = body_xml('''
            def main():
                x = 10
                while True:
                    # fg: breakpoint
                    if x <= 0:  # fg: comment explicit on exit line
                        break
                    x -= 3
        ''')
        self.assertIn('<while expression="x &gt; 0">\n<breakpoint/>\n<comment text="explicit on exit line"/>', body)
        body = body_xml('''
            def main():
                a = 1
                if a > 0:
                    print("pos")
                    # end of positive branch
                # before b
                b = 2
        ''')
        self.assertIn('<comment text="end of positive branch"/>\n</then>', body)
        self.assertIn('</if>\n<comment text="before b"/>', body)
        xml = conv("def add(a: int,  # the first\n        b: int) -> int:  # the second\n    return a + b\n\n"
                   "def main():\n    print(add(1, 2))\n")
        self.assertIn('<comment text="the first"/>', xml)
        self.assertIn('<comment text="the second"/>', xml)

    def test_tool_comments_are_not_shapes(self):  # L7, L8
        body = body_xml("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nx = 1  # noqa: F841\n"
                        "print(x)  # type: ignore\n# a real comment\n")
        self.assertEqual(re.findall(r'<comment text="([^"]*)"', body), ["a real comment"])

    # ---- output, names, XML --------------------------------------------------------------------
    def test_empty_input_prompt_shows_nothing(self):  # L5
        xml = same_as_python(self, 'def main():\n    s = input("")\n    t = input()\n    print(s, t)\n', ["a", "b"])
        self.assertNotIn('<output expression="&quot;&quot;"', xml)

    def test_control_characters_in_comments_keep_the_xml_well_formed(self):  # L6
        xml = conv('def main():\n    # bell \x07 here\n    print(1)\n')
        ET.fromstring(xml)
        self.assertIn('<comment text="bell  here"/>', xml)

    def test_unicode_identifiers_are_transliterated(self):  # L19
        body = body_xml("def main():\n    größe = 3\n    счёт = 4\n    print(größe, счёт)\n")
        self.assertIn('<declare name="grosse, schet" type="Integer"', body)

    def test_returned_list_and_bad_string_annotations_have_clear_errors(self):
        self.assertIn("functions cannot return arrays",
                      error_of("def f():\n    xs = [1, 2]\n    return xs\n\ndef main():\n    f()\n"))
        self.assertIn("invalid type annotation 'int('", error_of('def main():\n    x: "int(" = 3\n'))
        self.assertIn("invalid type annotation 'int('",
                      error_of('def f(x: "int(") -> int:\n    return 1\n\ndef main():\n    print(f(1))\n'))

    def test_nested_lists_and_module_variables_have_clear_errors(self):  # L20, L21
        self.assertIn("nested lists are not supported", error_of("def main():\n    xs = [[0] * 3] * 3\n"))
        self.assertIn("'x' is a module-level variable",
                      error_of("x = 5\n\ndef f() -> int:\n    return x\n\nx = 10\nprint(f())\n"))


class ProjectLayoutTest(unittest.TestCase):
    """Entry points, imports and files (bug-hunt leads about project layouts)."""

    def make_project(self, files: dict) -> str:
        root = tempfile.mkdtemp(prefix="py2fprg_")
        for rel, content in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(content if isinstance(content, bytes) else textwrap.dedent(content).encode())
        return root

    def convert(self, files: dict, target: str = "", **kw) -> list[tuple[str, str]]:
        root = self.make_project(files)
        outputs = convert_path(os.path.join(root, target) if target else root, metadata=False, **kw)
        for _, xml in outputs:
            lint_ok(xml)
        return [(os.path.relpath(p, root), xml) for p, xml in outputs]

    GUARD = '\nif __name__ == "__main__":\n    main()\n'

    def test_guard_decides_the_entry(self):
        (path, xml), = self.convert({"run.py": "from game import main\n" + self.GUARD,
                                     "game.py": 'def main():\n    print("game")\n'})
        self.assertEqual(path, "run.fprg")  # a launcher module that imports main()
        self.assertIn('<output expression="&quot;game&quot;"', xml)
        (_, xml), = self.convert({"prog.py": 'def run():\n    print("run")\n\nif __name__ == "__main__":\n    run()\n'})
        self.assertIn('<function name="Main" type="None" variable="">', xml)
        self.assertIn("&quot;run&quot;", xml)
        (_, xml), = self.convert({"prog.py": 'import sys\n\ndef main():\n    print(1)\n\n'
                                             'if __name__ == "__main__":\n    sys.exit(main())\n'})
        self.assertIn('<output expression="1"', xml)
        (_, xml), = self.convert({"prog.py": 'def main():\n    print(1)\n\nmain()\n'})
        self.assertIn('<output expression="1"', xml)
        # a block that does more than call main() is Main itself, and main() an ordinary function
        (_, xml), = self.convert({"prog.py": 'def main(n: int):\n    print(n)\n\nif __name__ == "__main__":\n'
                                             '    print("starting")\n    for k in range(2):\n        main(k)\n'})
        self.assertIn('<function name="mainVal" type="None" variable="">', xml)
        self.assertIn('<call expression="mainVal(k)"/>', xml)
        with self.assertRaises(ConvertError) as cm:  # names the block assigns are module variables
            self.convert({"prog.py": 'def show():\n    print(level)\n\nif __name__ == "__main__":\n'
                                     '    level = 3\n    show()\n'})
        self.assertIn("'level' is a module-level variable", str(cm.exception))

    def test_two_programs_may_call_each_others_main(self):
        outputs = self.convert({"a.py": 'def main():\n    print("a")\n' + self.GUARD,
                                "b.py": 'import a\n\ndef main():\n    a.main()\n    print("b")\n' + self.GUARD})
        self.assertEqual([p for p, _ in outputs], ["a.fprg", "b.fprg"])
        self.assertIn('<call expression="mainVal()"/>', outputs[1][1])

    def test_script_with_a_helper_module(self):
        outputs = self.convert({"script.py": "from helper import double\nx = 4\nprint(double(x))\n",
                                "helper.py": "def double(n: int) -> int:\n    return n * 2\n"})
        self.assertEqual([p for p, _ in outputs], ["script.fprg"])
        self.assertIn('<function name="double" type="Integer"', outputs[0][1])

    def test_package_imports(self):
        (path, xml), = self.convert({
            "pkg/__init__.py": "from .impl import helper\n\ndef main():\n    helper()\n" + self.GUARD,
            "pkg/impl.py": 'def helper():\n    print("helped")\n',
        }, "pkg/__init__.py")
        self.assertIn('<function name="helper"', xml)
        (_, xml), = self.convert({
            "game/app.py": "from . import helpers\n\ndef main():\n    helpers.greet()\n" + self.GUARD,
            "game/helpers.py": 'def greet():\n    print("hi")\n',
        }, "game")
        self.assertIn('<function name="greet"', xml)
        (_, xml), = self.convert({
            "prog.py": 'from tools import shout\n\ndef main():\n    shout("x")\n' + self.GUARD,
            "tools/__init__.py": "from .text import shout\n",
            "tools/text.py": "def shout(s: str):\n    print(s)\n",
        })
        self.assertIn('<function name="shout"', xml)  # re-exported by the package

    def test_sibling_module_wins_over_one_higher_up(self):
        (_, xml), = self.convert({
            "prompts.py": "def ask() -> int:\n    return 1\n",
            "app/quiz.py": "from prompts import ask\n\ndef main():\n    print(ask())\n" + self.GUARD,
            "app/prompts.py": "def ask() -> int:\n    return 2\n",
        }, "app/quiz.py")
        self.assertIn('<assign variable="result" expression="2"/>', xml)

    def test_source_encodings(self):
        warnings: list = []
        (_, xml), = self.convert({
            "prog.py": '# -*- coding: latin-1 -*-\ndef main():\n    print("caf\xe9")\n'.encode("latin-1") +
                       self.GUARD.encode(),
            "broken.py": b"x = '\xff\xfe'\n",
        }, warnings=warnings)
        self.assertIn("caf&#233;", xml)
        self.assertTrue(any("skipped broken.py" in w.msg for w in warnings))

    def test_dotted_import_through_a_folder_without_init(self):
        (_, xml), = self.convert({
            "app/prog.py": "import lib.tools\n\ndef main():\n    lib.tools.greet()\n" + self.GUARD,
            "app/lib/tools.py": 'def greet():\n    print("hi")\n',
        })
        self.assertIn('<function name="greet"', xml)

    def test_last_binding_of_a_module_name_wins(self):
        (_, xml), = self.convert({
            "prog.py": "LIMIT = 1\nfrom conf import LIMIT\n\ndef main():\n    print(LIMIT)\n" + self.GUARD,
            "conf.py": "LIMIT = 2\n",
        })
        self.assertIn('<assign variable="LIMIT" expression="2"/>', xml)
        (_, xml), = self.convert({
            "prog.py": "from conf import LIMIT\nLIMIT = 3\n\ndef main():\n    print(LIMIT)\n" + self.GUARD,
            "conf.py": "LIMIT = 2\n",
        })
        self.assertIn('<assign variable="LIMIT" expression="3"/>', xml)

    def test_module_level_code_of_an_imported_module_warns(self):
        warnings: list = []
        self.convert({"prog.py": "from helper import double\n\ndef main():\n    print(double(2))\n" + self.GUARD,
                      "helper.py": 'print("loading")\n\ndef double(n: int) -> int:\n    return n * 2\n'},
                     warnings=warnings)
        self.assertTrue(any("module-level code in helper.py" in w.msg for w in warnings))


if __name__ == "__main__":
    unittest.main()
