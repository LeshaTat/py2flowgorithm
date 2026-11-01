"""Tests for the py2fprg converter (run in the converter's folder:
python3 -m unittest discover -s tests).

Programs are written in the Flowgorithm dialect: one file, `from flowgorithm import *`, typed
functions, main(). Every converted document is linted, and the differential tests run the Python
program (with the flowgorithm library) and the flowchart (with fprg_run) on the same input: the
console text must be identical.
"""
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))  # the converter under test
LIBRARY = os.path.join(os.path.dirname(ROOT), "library", "src")  # the flowgorithm library next to this project
if os.path.isdir(LIBRARY):  # (a converter copied out of the repository uses the installed library)
    sys.path.insert(1, LIBRARY)

import fprg_lint  # noqa: E402
import fprg_run  # noqa: E402
from py2fprg import ConvertError, convert_path, convert_source  # noqa: E402
from py2fprg.cli import main as cli_main  # noqa: E402

ALLOWED = {
    "flowgorithm": {"fileversion"}, "attributes": set(), "attribute": {"name", "value"},
    "function": {"name", "type", "variable"}, "parameters": set(), "parameter": {"name", "type", "array"},
    "body": set(), "declare": {"name", "type", "array", "size"}, "assign": {"variable", "expression"},
    "input": {"variable"}, "output": {"expression", "newline"}, "if": {"expression"}, "then": set(),
    "else": set(), "while": {"expression"}, "do": {"expression"}, "call": {"expression"},
    "for": {"variable", "start", "end", "direction", "step"}, "comment": {"text"}, "breakpoint": set(),
}


def program(main_body: str, functions: str = "", top: str = "") -> str:
    """A complete dialect program around a main() body (and optional functions / constants)."""
    return (f'"""Test program."""\nfrom flowgorithm import *\n\n{textwrap.dedent(top)}\n'
            f"{textwrap.dedent(functions)}\n\ndef main():\n{textwrap.indent(textwrap.dedent(main_body), '    ')}"
            f'\n\nif __name__ == "__main__":\n    main()\n')


def conv(code: str, **kw) -> str:
    kw.setdefault("metadata", False)
    xml = convert_source(code, "prog", **kw)
    root = ET.fromstring(xml)
    for el in root.iter():
        assert el.tag in ALLOWED, el.tag
        assert set(el.attrib) <= ALLOWED[el.tag], (el.tag, el.attrib)
    errors = [f for f in fprg_lint.lint_string(xml, "prog.fprg") if f.severity == "ERROR"]
    assert not errors, "\n".join(map(str, errors)) + "\n" + xml
    return xml


def body_of(xml: str, function: str = "Main") -> str:
    m = re.search(rf'<function name="{function}".*?<body>(.*?)</body>', xml, re.S)
    assert m, xml
    return "\n".join(line.strip() for line in m.group(1).strip().splitlines())


def main_body(body: str, **kw) -> str:
    return body_of(conv(program(body, **kw)))


def error_of(code: str) -> str:
    try:
        convert_source(code, "prog", metadata=False)
    except ConvertError as e:
        return e.format()
    raise AssertionError("expected a ConvertError")


def run_python(code: str, inputs=(), randoms=()) -> str:
    """Run the program in Python with the flowgorithm library, scripted input and Random() values."""
    answers, rolls = iter(inputs), iter(randoms)
    out = io.StringIO()
    ns = {"__name__": "prog"}
    with patch("builtins.input", side_effect=lambda *a: next(answers)), \
            patch("random.randrange", side_effect=lambda n: next(rolls) % n), contextlib.redirect_stdout(out):
        exec(compile(code, "prog.py", "exec"), ns)
        ns["main"]()
    return out.getvalue()


def same_as_python(test: unittest.TestCase, code: str, inputs=(), randoms=()) -> str:
    xml = conv(code)
    expected = run_python(code, inputs, randoms)
    test.assertEqual(expected, fprg_run.run_string(xml, list(inputs), random_values=list(randoms)), xml)
    return xml


Q = "&quot;"


class StructureTest(unittest.TestCase):
    def test_skeleton_title_and_about(self):
        xml = conv('"""Number Guesser.\n\nGuess a number."""\nfrom flowgorithm import *\n\n\ndef main():\n'
                   '    Output("hi")\n\n\nif __name__ == "__main__":\n    main()\n')
        self.assertTrue(xml.startswith('<?xml version="1.0"?>\n<flowgorithm fileversion="3.0">\n'))
        self.assertIn('<attribute name="name" value="Number Guesser"/>', xml)
        self.assertIn('<attribute name="about" value="Number Guesser.&#13;&#10;&#13;&#10;Guess a number."/>', xml)
        self.assertIn('<function name="Main" type="None" variable="">', xml)

    def test_functions_follow_main_in_source_order(self):
        xml = conv(program("Output(first(1), second(2))", functions='''
            def first(n: int) -> int:
                return n + 1

            def second(n: int) -> int:
                return first(n) * 2
        '''))
        self.assertEqual(re.findall(r'<function name="(\w+)"', xml), ["Main", "first", "second"])

    def test_structure_errors(self):
        cases = {
            'import random\n\ndef main():\n    pass\n': "imports only the library",
            'from flowgorithm import *\nprint("x")\n\ndef main():\n    pass\n': "at the top of the program",
            'from flowgorithm import *\n\ndef helper():\n    pass\n': "needs a `def main():`",
            'from flowgorithm import *\n\ndef main(n: int):\n    pass\n': "main() takes no parameters",
            'from flowgorithm import *\n\ndef main():\n    pass\n\nif __name__ == "__main__":\n'
            '    Output("x")\n    main()\n': "only calls main()",
            'from flowgorithm import *\n\ndef f(n):\n    pass\n\ndef main():\n    pass\n': "needs a type",
            'from flowgorithm import *\n\ndef f(n: int = 1):\n    pass\n\ndef main():\n    pass\n': "no default values",
            'from flowgorithm import *\nX = 1\nX = 2\n\ndef main():\n    pass\n': "set twice",
            'from flowgorithm import *\nX = [1]\n\ndef main():\n    pass\n': "a constant is a literal value",
        }
        for code, msg in cases.items():
            with self.subTest(msg=msg):
                self.assertIn(msg, error_of(code))

    def test_constants_are_copied_into_the_functions_using_them(self):
        xml = conv(program("Output(LIMIT, twice())", top="LIMIT = 10\nNAME = \"Quiz\"\n", functions='''
            def twice() -> int:
                return LIMIT * 2
        '''))
        self.assertIn('<assign variable="LIMIT" expression="10"/>', body_of(xml))
        self.assertIn('<assign variable="LIMIT" expression="10"/>', body_of(xml, "twice"))
        self.assertNotIn("NAME", xml)
        self.assertIn("is a constant", error_of(program("LIMIT = 3", top="LIMIT = 10\n")))


class StatementTest(unittest.TestCase):
    def test_output_and_input(self):
        body = main_body('''
            Output("Name?")
            name = Input(str)
            Output("Age?", newline=False)
            age = Input(int)
            height = Input(float)
            ok = Input(bool)
            Output("Hello ", name, ", ", age + 1)
            Output()
        ''')
        self.assertIn(f'<output expression="{Q}Name?{Q}" newline="True"/>\n<input variable="name"/>', body)
        self.assertIn(f'<output expression="{Q}Age?{Q}" newline="False"/>', body)
        self.assertIn(f'<output expression="{Q}Hello {Q} &amp; name &amp; {Q}, {Q} &amp; age + 1" newline="True"/>',
                      body)
        self.assertIn(f'<output expression="{Q}{Q}" newline="True"/>', body)
        self.assertIn('<declare name="height" type="Real"', body)
        self.assertIn('<declare name="ok" type="Boolean"', body)

    def test_declarations_are_hoisted_and_grouped(self):
        body = main_body('n = 1\nx = 2.5\nname = "a"\nflag = True\nm = n + 1\ny: float = 0\nk: int\nk = 3')
        self.assertEqual(body.splitlines()[:4], [
            '<declare name="n, m, k" type="Integer" array="False" size=""/>',
            '<declare name="x, y" type="Real" array="False" size=""/>',
            '<declare name="name" type="String" array="False" size=""/>',
            '<declare name="flag" type="Boolean" array="False" size=""/>'])

    def test_a_variable_keeps_its_type(self):
        self.assertIn("is an Integer but gets a Real", error_of(program("total = 0\ntotal = total + 0.5")))
        self.assertIn("is String but gets Integer", error_of(program('s = "a"\ns = 1')))
        body = main_body("x = 0.0\nx = x + 1\nn: float = 0\nn = n + 0.5")  # Integer into Real is fine
        self.assertIn('<assign variable="x" expression="x + 1"/>', body)

    def test_hints_name_what_to_change(self):
        functions = "def half(n: int) -> int:\n    return n\n\ndef show(n: int):\n    Output(n)\n"
        cases = {
            "total = 0\ntotal = total + 0.5": "make total a Real from the start (total = 0.0",
            "xs = [0] * 3\nxs[0] = 2.5": "make xs an array of Reals from the start (xs = [0.0] * n)",
            "show(2.5)": "make the parameter a Real (n: float)",
            "x = 0\nx = Input(float)": "or make x a Real from the start",
            'x = int(input("Number? "))': "read it with x = Input(int); show the question with Output(...) first",
            "import math": "the flowgorithm library has the math functions",
            "try:\n    pass\nexcept ValueError:\n    pass": "check the value with an if",
        }
        for code, msg in cases.items():
            with self.subTest(code=code):
                self.assertIn(msg, error_of(program(code, functions=functions)))
        self.assertIn("let it return a Real (def half(...) -> float:)",
                      error_of(program("pass", functions="def half(n: int) -> int:\n    return n / 2\n")))

    def test_augmented_assignment(self):
        body = main_body('n = 1\nn += 2\nn *= 3\ns = "a"\ns += "b"')
        self.assertIn('<assign variable="n" expression="n + 2"/>', body)
        self.assertIn('<assign variable="n" expression="n * 3"/>', body)
        self.assertIn('<assign variable="s" expression="s &amp; ' + Q + 'b' + Q + '"/>', body)

    def test_arrays(self):
        body = main_body('''
            n = 3
            xs = [0] * n
            names = [""] * 2
            flags: list[bool] = [False] * 4
            ys = [1.5, 2.5]
            xs[0] = Input(int)
            xs[1] = xs[0] * 2
            Output(Size(xs), ys[1])
        ''')
        self.assertIn('<declare name="xs" type="Integer" array="True" size="n"/>', body)
        self.assertIn('<declare name="names" type="String" array="True" size="2"/>', body)
        self.assertIn('<declare name="flags" type="Boolean" array="True" size="4"/>', body)
        self.assertIn('<declare name="ys" type="Real" array="True" size="2"/>\n<assign variable="ys[0]" '
                      'expression="1.5"/>', body)
        self.assertIn('<input variable="xs[0]"/>', body)
        for code, msg in {"xs = [1] * 3": "starts out as 0", "xs = [0] * 3\nxs[0] = 0.5": "is an Integer but gets",
                          "xs = [0] * 3\nOutput(xs[-1])": "no negative indexes", "xs = [0] * 3\nys = xs": "cannot be copied",
                          "xs = []": "needs a size", "s = \"ab\"\nOutput(s[0])": "Char(text, i)",
                          "for k in range(2):\n    row = [0] * 3": "the array 'row' is made inside a loop"}.items():
            with self.subTest(code=code):
                self.assertIn(msg, error_of(program(code)))

    def test_if_elif_else(self):
        body = main_body('''
            n = Input(int)
            if n > 0:
                Output("positive")
            elif n == 0:
                Output("zero")
            else:
                Output("negative")
        ''')
        self.assertIn('<if expression="n &gt; 0">\n<then>\n<output expression="' + Q + 'positive' + Q, body)
        self.assertIn('<else>\n<if expression="n == 0">', body)

    def test_while_and_do(self):
        body = main_body('''
            n = 10
            while n > 0:
                n = n - 3
            while True:
                Output("Again?")
                answer = Input(str)
                if answer == "n":
                    break
        ''')
        self.assertIn('<while expression="n &gt; 0">', body)
        self.assertIn('<do expression="answer != ' + Q + 'n' + Q + '">', body)
        # the condition to repeat is written without `not` where it can be (De Morgan's rule)
        body = main_body('''
            done = False
            while True:
                n = Input(int)
                if n >= 1 and n <= 100:
                    break
            while True:
                n = Input(int)
                if done or not (n > 5):
                    break
        ''')
        self.assertIn('<do expression="n &lt; 1 or n &gt; 100">', body)
        self.assertIn('<do expression="not done and n &gt; 5">', body)
        self.assertIn("Do loop", error_of(program("while True:\n    if 1 > 0:\n        break\n    Output(1)")))
        self.assertIn("break only ends", error_of(program("n = 0\nwhile n < 3:\n    break")))
        self.assertIn("continue is not part", error_of(program("for i in range(3):\n    continue")))

    def test_for_loops(self):
        body = main_body('''
            n = 5
            for i in range(n):
                Output(i)
            for i in range(1, n + 1):
                Output(i)
            for k in range(10, 0, -2):
                Output(k)
            for j in range(2, 2 * n, 3):
                Output(j)
        ''')
        self.assertIn('<for variable="i" start="0" end="n - 1" direction="inc" step="1">', body)
        self.assertIn('<for variable="i" start="1" end="n" direction="inc" step="1">', body)
        self.assertIn('<for variable="k" start="10" end="1" direction="dec" step="2">', body)
        self.assertIn('<for variable="j" start="2" end="2 * n - 1" direction="inc" step="3">', body)
        for code, msg in {"for i in range(3):\n    i = 5": "changed inside its loop",
                          "for i in range(3):\n    for i in range(2):\n        pass": "enclosing for loop",
                          "xs = [0] * 2\nfor x in xs:\n    pass": "counts with range()",
                          "n = 2\nfor i in range(0, 9, n):\n    pass": "written as a number",
                          "n = 3\nfor i in range(n):\n    n = n - 1": "the loop changes 'n', which range() counts to",
                          "xs = [0] * 2\nfor i in range(xs[0]):\n    xs[1] = i": "the loop changes 'xs'"}.items():
            with self.subTest(code=code):
                self.assertIn(msg, error_of(program(code)))
        main_body("xs = [0] * 3\nfor i in range(Size(xs)):\n    xs[i] = i")  # an array keeps its size

    def test_a_for_variable_after_its_loop(self):
        # Flowgorithm's counter ends one step past Python's last value: it gets a new value first
        cases = {
            "for i in range(3):\n    pass\nOutput(i)": "'i' is read after its for loop (line 8)",
            "n = Input(int)\ni = 0\nif n > 0:\n    for i in range(n):\n        pass\nOutput(i)": "after its for loop",
            "for i in range(3):\n    pass\ni += 1": "after its for loop",
            "i = 0\nn = 0\nwhile n < 3:\n    Output(i)\n    for i in range(2):\n        n = n + 1":
                "'i' is read here when the loop repeats, after its for loop (line 12)",
            "i = 0\nwhile i < 3:\n    for i in range(2):\n        pass": "when the loop repeats",
            "j = 0\nfor t in range(3):\n    if t > 0:\n        Output(j)\n    for j in range(2):\n        pass":
                "when the loop repeats",
        }
        for code, msg in cases.items():
            with self.subTest(code=code):
                self.assertIn(msg, error_of(program(code)))
        main_body("for t in range(3):\n    j = 0\n    if t > 0:\n        Output(j)\n    for j in range(2):\n        pass")
        self.assertIn("give the variable a new value first", error_of(program("for i in range(3):\n    pass\n"
                                                                              "Output(i)")))

    def test_input_reads_the_type_of_its_variable(self):
        self.assertIn("'x' is Real: read it with Input(float)", error_of(program("x = 0.0\nx = Input(int)")))
        self.assertIn("'n' is Integer: read it with Input(int)", error_of(program("n: int = Input(float)")))
        self.assertIn("an element of xs is Integer: read it with Input(int)",
                      error_of(program("xs = [0] * 2\nxs[0] = Input(str)")))

    def test_functions_and_returns(self):
        xml = conv(program("Output(square(3), average(4, 5))\nshow(\"x\")", functions='''
            def square(n: int) -> int:
                result = n * n
                return result

            def average(a: int, b: int) -> float:
                return (a + b) / 2

            def show(text: str):
                Output("[", text, "]")
        '''))
        self.assertIn('<function name="square" type="Integer" variable="result">', xml)
        self.assertIn('<function name="average" type="Real" variable="result">', xml)
        self.assertIn('<assign variable="result" expression="(a + b) / 2"/>', body_of(xml, "average"))
        self.assertIn('<call expression="show(' + Q + 'x' + Q + ')"/>', body_of(xml))
        self.assertIn("return must be the last statement", error_of(program("pass", functions='''
            def f(n: int) -> int:
                if n > 0:
                    return 1
                return 0
        ''')))
        self.assertIn("returns no value", error_of(program("x = show()", functions="def show():\n    Output(1)\n")))
        self.assertIn("not known here (it calls itself)", error_of(program("Output(f(3))", functions='''
            def f(n: int):
                total = 1
                if n > 1:
                    total = n * f(n - 1)
                return total
        ''')))

    def test_recursion_with_an_annotation(self):
        same_as_python(self, program("Output(fact(5))", functions='''
            def fact(n: int) -> int:
                result = 1
                if n > 1:
                    result = n * fact(n - 1)
                return result
        '''))

    def test_comments_and_directives(self):
        body = body_of(conv(program('''
            # ask for the number
            n = Input(int)  # read it
            # fg: breakpoint
            # fg: comment checked below
            if n > 0:
                Output("positive")
                # end of the positive branch
            Output("debug", n)  # fg: ignore
        ''')))
        self.assertIn('<comment text="ask for the number"/>\n<comment text="read it"/>\n<input variable="n"/>', body)
        self.assertIn('<breakpoint/>\n<comment text="checked below"/>\n<if', body)
        self.assertIn('<comment text="end of the positive branch"/>\n</then>', body)
        self.assertNotIn("debug", body)

    def test_warnings_where_flowgorithm_may_differ(self):
        def warnings_of(body: str, functions: str = "") -> list:
            found: list = []
            convert_source(program(body, functions=functions), "prog", warnings=found, metadata=False)
            return [w.msg for w in found]

        self.assertIn("the index in xs[i] must work then too",
                      warnings_of("xs = [0] * 3\ni = 0\nwhile i < Size(xs) and xs[i] != 5:\n    i = i + 1")[0])
        self.assertIn("the division in 10 / n", warnings_of("n = 0\nif n == 0 or 10 / n > 2:\n    pass")[0])
        self.assertIn("ask()", warnings_of("ok = False\nif ok and ask():\n    pass",
                                           "def ask() -> bool:\n    answer = Input(str)\n    return answer == \"y\"\n")[0])
        self.assertIn("Python orders Strings by character code", warnings_of('s = "a"\nif s < "B":\n    pass')[0])
        self.assertEqual(warnings_of('i = 0\nok = True\ns = "a"\nif i < 3 and ok or s == "b":\n    pass'), [])
        # a renamed name is reported, unless only its spelling changed (snake_case -> camelCase)
        self.assertEqual(warnings_of("size = 2\nmy_total = 1\nOutput(size, my_total, half(2))",
                                     "def half(real: float) -> float:\n    return real / 2\n"),
                         ["parameter 'real' is called 'realVal' in the flowchart ('real' is a Flowgorithm word)",
                          "variable 'size' is called 'sizeVal' in the flowchart ('size' is a Flowgorithm word)"])
        self.assertIn("the name clashes", warnings_of("total = 1\nTotal = 2\nOutput(total, Total)")[0])


class ExpressionTest(unittest.TestCase):
    def expr(self, text: str, setup: str = 'a = 1\nb = 2\nc = 3\ns = "x"\nx = 1.5\nok = True\nxs = [0] * 3') -> str:
        body = main_body(f"{setup}\nr = {text}")
        return re.search(r'<assign variable="r" expression="([^"]*)"/>', body).group(1) \
            .replace(Q, '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

    def test_arithmetic_and_precedence(self):
        self.assertEqual(self.expr("a + b * c"), "a + b * c")
        self.assertEqual(self.expr("(a + b) * c"), "(a + b) * c")
        self.assertEqual(self.expr("a - (b - c)"), "a - (b - c)")
        self.assertEqual(self.expr("a ** 2"), "a ^ 2")
        self.assertEqual(self.expr("-(a + b)"), "-(a + b)")
        self.assertEqual(self.expr("a % 2"), "a % 2")
        self.assertEqual(self.expr("x / 2"), "x / 2")

    def test_powers(self):
        self.assertEqual(self.expr("2 ** 3 ** 2"), "2 ^ (3 ^ 2)")
        self.assertEqual(self.expr("(-a) ** 2"), "(-a) ^ 2")  # a sign binds tighter than ^ in Flowgorithm
        self.assertEqual(self.expr("-a ** 2"), "-(a ^ 2)")
        self.assertEqual(self.expr("a ** -b"), "a ^ (-b)")
        # Integer only with a whole-number exponent written out: 2 ** b is a Real when b < 0
        body = main_body("a = 2\nb = 3\nsquare = a ** 2\npower = a ** b\nroot = a ** 0.5")
        self.assertIn('<declare name="a, b, square" type="Integer"', body)
        self.assertIn('<declare name="power, root" type="Real"', body)
        self.assertIn("Int(...)", error_of(program("a = 2\nb = 3\nxs = [0] * 9\nxs[a ** b] = 1")))

    def test_logic_and_comparison(self):
        self.assertEqual(self.expr("a < b and not ok or c == 3"), "a < b and not ok or c == 3")
        self.assertEqual(self.expr("(a < b or ok) and c != 2"), "(a < b or ok) and c != 2")

    def test_strings(self):
        self.assertEqual(self.expr('s + "!" + ToString(a)'), 's & "!" & ToString(a)')
        self.assertEqual(self.expr('"say \\"hi\\""'), '"say " & ToChar(34) & "hi" & ToChar(34)')

    def test_library_functions(self):
        self.assertEqual(self.expr("Len(s) + Size(xs)"), "Len(s) + Size(xs)")
        self.assertEqual(self.expr("ToFixed(x, 2)"), "ToFixed(x, 2)")
        self.assertEqual(self.expr("Int(x) + Random(6)"), "Int(x) + Random(6)")
        self.assertEqual(self.expr("Sqrt(pi)"), "Sqrt(pi)")
        self.assertEqual(self.expr("Char(s, 0)"), "Char(s, 0)")

    def test_what_is_not_part_of_the_dialect(self):
        cases = {
            "print(1)": "use Output(...)", "n = input()": "use Input(int)", "n = len(s)": "use Len(text)",
            "n = int(s)": "use ToInteger(text)", 'n = "a" + 1': "joined with ToString()", "n = 7 // 2": "Int(a / b)",
            "n = 1 if ok else 2": "use an if statement", 'n = f"{a}"': "pass the values to Output",
            "n = s.upper()": "methods", "n = 1 < a < 3": "two values at a time", "n = a and b": "true or false",
            "n = 1e-9": "no plain decimal form", "n = Len(5)": "needs a String", "n = Char(s)": "takes 2 arguments",
            "n = Input()": "", "if a:\n    pass": "a condition is true or false", "a, b = b, a": "one variable at a time",
            "n = Random": "is not a value", "n = q": "used before it gets a value", "n = x in xs": "comparisons are not part",
            "if (n := 3) > a:\n    pass": "assignment expressions (:=)", "n = {1, 2}": "sets",
            "n = ToInteger(2.5)": "Int(x) cuts off the fraction", "n = ToReal(a)": "goes into a Real variable",
            "n = ToString(ok)": "ToString() turns a number into text", "n = ToString(s)": "needs a number",
        }
        setup = 'a = 1\nb = 2\ns = "x"\nok = True\nxs = [0] * 3\n'
        for code, msg in cases.items():
            if code == "n = Input()":  # Input() without a type reads a String: fine
                conv(program(setup + code))
                continue
            with self.subTest(code=code):
                self.assertIn(msg, error_of(program(setup + code)))


class DifferentialTest(unittest.TestCase):
    """Python with the flowgorithm library and the generated flowchart print exactly the same."""

    def test_number_formatting_and_booleans(self):
        same_as_python(self, program('''
            half = 7 / 2
            whole = 6 / 2
            Output(half, " ", whole, " ", 2 ** -1, " ", 1 > 0, " ", ToFixed(2.675, 2))
            Output(Int(-3.7), " ", ToInteger("42") + 1, " ", ToString(0.1 + 0.2))
        '''))

    def test_interactive_program(self):
        same_as_python(self, program('''
            Output("How many numbers?")
            n = Input(int)
            total = 0.0
            for i in range(n):
                Output("Number ", i + 1, "?")
                value = Input(float)
                total = total + value
            Output("Average: ", total / n)
            largest = 0
            while True:
                Output("Again? (y/n)")
                answer = Input(str)
                if answer == "y" or answer == "n":
                    break
        '''), ["3", "1.5", "2", "4", "maybe", "n"])

    def test_functions_arrays_and_random(self):
        same_as_python(self, program('''
            rolls = [0] * 6
            for k in range(20):
                face = Random(6)
                rolls[face] = rolls[face] + 1
            for face in range(Size(rolls)):
                Output(face + 1, ": ", stars(rolls[face]))
        ''', functions='''
            def stars(n: int) -> str:
                line = ""
                for i in range(n):
                    line = line + "*"
                return line
        '''), randoms=list(range(20)))

    def test_for_variables_with_new_values(self):
        same_as_python(self, program('''
            for i in range(3):
                Output(i)
            i = 10
            Output(i)
            for row in range(4):
                total = 0
                for col in range(row):
                    total = total + col
                col = row * 2
                Output(row, " ", total, " ", col)
            xs = [0] * 3
            for k in range(Size(xs)):
                xs[k] = k * k
            for k in range(Size(xs) - 1, -1, -1):
                Output(xs[k])
        '''))


class CommandLineTest(unittest.TestCase):
    def test_a_folder_of_exercises(self):
        root = tempfile.mkdtemp(prefix="py2fprg_")
        files = {"ex1.py": program('Output("one")'), "ex2.py": program('Output("two")'),
                 "test_ex1.py": "import ex1\n", "flowgorithm.py": "# the library copy\n",
                 "notes.py": "x = 1\n"}
        for name, text in files.items():
            with open(os.path.join(root, name), "w") as fh:
                fh.write(text)
        outputs = convert_path(root, metadata=False)
        self.assertEqual([os.path.basename(p) for p, _ in outputs], ["ex1.fprg", "ex2.fprg"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli_main([os.path.join(root, "ex1.py"), "--check", "--lint"]), 0)
        self.assertIn("ok: ex1.fprg", out.getvalue())
        err = io.StringIO()
        with open(os.path.join(root, "bad.py"), "w") as fh:
            fh.write(program("print(1)"))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cli_main([os.path.join(root, "bad.py")]), 1)
        self.assertRegex(err.getvalue(), r"bad\.py:\d+:5: error: print\(\) is not part of the Flowgorithm dialect")
        self.assertIn("hint: use Output(...)", err.getvalue())
        # a whole folder (and more paths): a program with an error does not stop the others
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli_main([root, os.path.join(root, "ex1.py"), "--check"]), 1)
        self.assertEqual(re.findall(r"ok: (\w+)\.fprg", out.getvalue()), ["ex1", "ex2", "ex1"])
        self.assertIn("bad.py", err.getvalue())
        self.assertIn("3 of 4 programs converted", err.getvalue())
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            cli_main([root, "-o", os.path.join(root, "all.fprg")])


if __name__ == "__main__":
    unittest.main()
