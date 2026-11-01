"""Unit tests for fprg_lint.py (run: python3 -m unittest tests.test_fprg_lint -v)."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fprg_lint  # noqa: E402
from fprg_lint import ERROR, WARNING, ExprError, Finding, Parser, lint_file, lint_string  # noqa: E402

HEADER = (
    '<?xml version="1.0"?>\n'
    '<flowgorithm fileversion="3.0">\n'
    '    <attributes>\n'
    '        <attribute name="name" value="test"/>\n'
    '        <attribute name="authors" value="tests"/>\n'
    '        <attribute name="about" value=""/>\n'
    '        <attribute name="saved" value="2024-01-01 12:00:00 PM"/>\n'
    '    </attributes>\n'
)


def program(main_body, extra_functions="", main_attrs='name="Main" type="None" variable=""'):
    """Wrap a Main body (and optional extra <function> elements) into a full .fprg document."""
    return (HEADER
            + f'    <function {main_attrs}>\n        <parameters/>\n        <body>\n{main_body}\n'
            + '        </body>\n    </function>\n'
            + extra_functions
            + '</flowgorithm>\n')


def errors(findings):
    return [f for f in findings if f.severity == ERROR]


def warnings(findings):
    return [f for f in findings if f.severity == WARNING]


class LintTestCase(unittest.TestCase):
    def assertNoErrors(self, findings):
        self.assertEqual(errors(findings), [], "unexpected errors:\n" + "\n".join(map(str, errors(findings))))

    def assertClean(self, findings):
        self.assertEqual(findings, [], "unexpected findings:\n" + "\n".join(map(str, findings)))

    def assertFinding(self, findings, severity, fragment, path=None):
        for f in findings:
            if f.severity == severity and fragment in f.message and (path is None or f.path == path):
                return f
        self.fail(f"no {severity} containing {fragment!r}"
                  + (f" at {path}" if path else "") + " in:\n" + "\n".join(map(str, findings)))

    def assertError(self, findings, fragment, path=None):
        return self.assertFinding(findings, ERROR, fragment, path)

    def assertWarning(self, findings, fragment, path=None):
        return self.assertFinding(findings, WARNING, fragment, path)


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------

class ValidProgramsTest(LintTestCase):
    def test_hello_world_is_clean(self):
        src = program('<output expression="&quot;Hello, World!&quot;" newline="True"/>')
        self.assertClean(lint_string(src))

    def test_all_statement_kinds_and_operator_spellings(self):
        body = """
            <comment text="demo"/>
            <declare name="n, i, total" type="Integer" array="False" size=""/>
            <declare name="x" type="Real" array="False" size=""/>
            <declare name="s" type="String" array="False" size=""/>
            <declare name="ok" type="Boolean" array="False" size=""/>
            <declare name="arr" type="Integer" array="True" size="10"/>
            <output expression="&quot;How many?&quot;" newline="False"/>
            <input variable="n"/>
            <assign variable="total" expression="0"/>
            <for variable="i" start="0" end="n - 1" direction="inc" step="1">
                <assign variable="arr[i]" expression="i * 2 + Random(5)"/>
                <assign variable="total" expression="total + arr[i]"/>
            </for>
            <assign variable="x" expression="Sqrt(total) + π × 2 ÷ 4 - Abs(-3) ↑ 2"/>
            <assign variable="s" expression="&quot;Total: &quot; &amp; total &amp; &quot; &quot; &amp; ToFixed(x, 2)"/>
            <assign variable="ok" expression="n ≥ 1 ∧ ¬(n ≠ 3) ∨ Len(s) &lt;= 3 and not false or true"/>
            <if expression="ok &amp;&amp; total &gt; 0 || n == 0">
                <then>
                    <output expression="s" newline="True"/>
                </then>
                <else/>
            </if>
            <while expression="total &lt;&gt; 0">
                <assign variable="total" expression="total - 1"/>
            </while>
            <do expression="total mod 2 = 1">
                <assign variable="total" expression="total % 3"/>
            </do>
            <breakpoint/>
            <call expression="Greet(s, arr, Size(arr))"/>
            <output expression="Char(s, 0) &amp; ToChar(65) &amp; ToCode(&quot;A&quot;) &amp; Int(x) &amp; Sgn(x) &amp; EOF()" newline="True"/>
            <output expression="Area(1.5) &amp; Cos(x) &amp; Sin(x) &amp; Tan(x) &amp; Arcsin(0) &amp; Arccos(0) &amp; Arctan(0) &amp; Ln(1) &amp; Log(1) &amp; Log10(1)" newline="True"/>
            <output expression="ToInteger(&quot;1&quot;) + ToReal(&quot;1.5&quot;) &amp; ToString(3) &amp; 1.5e3" newline="True"/>
        """
        functions = """
    <function name="Greet" type="None" variable="">
        <parameters>
            <parameter name="who" type="String" array="False"/>
            <parameter name="values" type="Integer" array="True"/>
            <parameter name="count" type="Integer" array="False"/>
        </parameters>
        <body>
            <output expression="who &amp; values[0] &amp; count" newline="True"/>
        </body>
    </function>
    <function name="Area" type="Real" variable="result">
        <parameters>
            <parameter name="radius" type="Real" array="False"/>
        </parameters>
        <body>
            <declare name="result" type="Real" array="False" size=""/>
            <assign variable="result" expression="Pi * radius ^ 2"/>
        </body>
    </function>
"""
        self.assertClean(lint_string(program(body, functions)))

    def test_declares_in_exclusive_branches_are_not_duplicates(self):
        body = """
            <declare name="choice" type="Integer" array="False" size=""/>
            <input variable="choice"/>
            <if expression="choice = 1">
                <then>
                    <declare name="height" type="Real" array="False" size=""/>
                    <input variable="height"/>
                </then>
                <else>
                    <if expression="choice = 2">
                        <then>
                            <declare name="height" type="Integer" array="False" size=""/>
                            <input variable="height"/>
                        </then>
                        <else/>
                    </if>
                </else>
            </if>
        """
        findings = lint_string(program(body))
        self.assertNoErrors(findings)
        self.assertEqual(len([w for w in warnings(findings) if "inside a block" in w.message]), 2)

    def test_legacy_1x_file_only_warns(self):
        src = ('<?xml version="1.0"?>\n<flowgorithm fileversion="1.0">\n'
               '<attributes><attribute name="name" value="x"/><attribute name="authors" value="x"/>'
               '<attribute name="about" value="x"/><attribute name="saved" value="x"/></attributes>\n'
               '<function name="Main" type="None" variable=""><parameters/><body>\n'
               '<declare variables="n" type="Integer"/>\n'
               '<for variable="n" start="1" end="100" step="1"><output expression="n"/></for>\n'
               '</body></function></flowgorithm>')
        findings = lint_string(src)
        self.assertNoErrors(findings)
        self.assertWarning(findings, "legacy attribute 'variables'", "Main/body[0]/declare")

    def test_both_name_and_variables_as_in_1_7_files(self):
        body = '<declare name="x" type="Integer" array="False" size="" variables="x"/>\n<output expression="x"/>'
        findings = lint_string(program(body))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "legacy attribute 'variables'")

    def test_function_used_before_definition_and_return_variable_as_parameter(self):
        body = '<output expression="Twice(2)" newline="True"/>'
        functions = """
    <function name="Twice" type="Integer" variable="n">
        <parameters><parameter name="n" type="Integer" array="False"/></parameters>
        <body><assign variable="n" expression="n * 2"/></body>
    </function>
"""
        self.assertClean(lint_string(program(body, functions)))

    def test_intrinsics_and_keywords_are_case_insensitive(self):
        body = ('<declare name="name" type="String" array="False" size=""/>\n'
                '<declare name="n" type="Integer" array="False" size=""/>\n'
                '<input variable="name"/>\n'
                '<for variable="n" start="0" end="len(name) - 1" direction="inc" step="1">\n'
                '<output expression="CHAR(name, n) &amp; (n MOD 2 = 0 AND TRUE)" newline="True"/>\n'
                '</for>')
        self.assertClean(lint_string(program(body)))

    def test_variable_may_share_name_with_function(self):
        body = '<call expression="carp(2, 3)"/>'
        functions = """
    <function name="carp" type="None" variable="">
        <parameters>
            <parameter name="a" type="Integer" array="False"/>
            <parameter name="b" type="Integer" array="False"/>
        </parameters>
        <body>
            <declare name="carp" type="Integer" array="False" size=""/>
            <assign variable="carp" expression="a * b"/>
            <output expression="carp" newline="True"/>
        </body>
    </function>
"""
        self.assertClean(lint_string(program(body, functions)))

    def test_lint_file_and_bytes_input(self):
        src = program('<output expression="&quot;hi&quot;" newline="True"/>')
        self.assertClean(lint_string(src.encode("ascii")))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "ok.fprg")
            with open(path, "w", encoding="ascii") as fh:
                fh.write(src)
            findings = lint_file(path)
            self.assertClean(findings)


# ---------------------------------------------------------------------------
# Negative tests: one per error class
# ---------------------------------------------------------------------------

class StructureErrorsTest(LintTestCase):
    def test_malformed_xml(self):
        findings = lint_string("<flowgorithm fileversion='3.0'><function></flowgorithm>")
        self.assertError(findings, "not well-formed XML")
        self.assertEqual(findings[0].path, "")

    def test_wrong_root(self):
        self.assertError(lint_string("<program/>"), "root element is <program>")

    def test_missing_fileversion(self):
        src = ('<flowgorithm><function name="Main" type="None" variable=""><parameters/><body/></function>'
               '</flowgorithm>')
        findings = lint_string(src)
        self.assertError(findings, "missing 'fileversion'", "flowgorithm")
        self.assertWarning(findings, "no <attributes> element", "flowgorithm")

    def test_missing_main(self):
        src = HEADER + ('<function name="Helper" type="None" variable=""><parameters/><body/></function>'
                        '</flowgorithm>')
        self.assertError(lint_string(src), "no Main function", "flowgorithm")

    def test_main_must_be_none_typed_without_parameters(self):
        src = (HEADER + '<function name="Main" type="Integer" variable="r"><parameters>'
               '<parameter name="p" type="Integer" array="False"/></parameters>'
               '<body><declare name="r" type="Integer" array="False" size=""/></body></function></flowgorithm>')
        findings = lint_string(src)
        self.assertError(findings, "Main must have type None", "Main")
        self.assertError(findings, "Main cannot have parameters", "Main")

    def test_duplicate_function_names_case_insensitive(self):
        functions = ('<function name="Foo" type="None" variable=""><parameters/><body/></function>'
                     '<function name="foo" type="None" variable=""><parameters/><body/></function>')
        findings = lint_string(program('<call expression="Foo()"/>', functions))
        self.assertError(findings, "duplicate function name 'foo'", "foo")

    def test_function_with_type_but_no_variable(self):
        functions = '<function name="F" type="Integer" variable=""><parameters/><body/></function>'
        findings = lint_string(program('<output expression="F()"/>', functions))
        self.assertError(findings, "has type Integer but no return variable", "F")

    def test_return_variable_must_be_declared(self):
        functions = ('<function name="F" type="Integer" variable="r"><parameters/>'
                     '<body><output expression="1"/></body></function>')
        findings = lint_string(program('<output expression="F()"/>', functions))
        self.assertError(findings, "return variable 'r' is never declared", "F")

    def test_bad_function_type(self):
        functions = '<function name="F" type="integer" variable="r"><parameters/><body/></function>'
        findings = lint_string(program('<output expression="1"/>', functions))
        self.assertError(findings, "did you mean 'Integer'", "F")

    def test_unknown_statement_element(self):
        findings = lint_string(program("<more/>"))
        self.assertError(findings, "unknown statement element <more>", "Main/body[0]/more")

    def test_unknown_root_child_and_missing_parts(self):
        src = HEADER + ('<junk/><function name="Main" type="None" variable=""><body/></function></flowgorithm>')
        findings = lint_string(src)
        self.assertError(findings, "unexpected element <junk>", "flowgorithm")
        self.assertError(findings, "missing <parameters>", "Main")

    def test_missing_then_and_else(self):
        findings = lint_string(program('<if expression="true"><then/></if>'))
        self.assertError(findings, "missing its <else>", "Main/body[0]/if")
        findings = lint_string(program('<if expression="true"><else/></if>'))
        self.assertError(findings, "missing its <then>", "Main/body[0]/if")
        findings = lint_string(program('<if expression="true"><else/><then/></if>'))
        self.assertError(findings, "<then> must come before <else>", "Main/body[0]/if")
        findings = lint_string(program('<if expression="true"><then/><else/><other/></if>'))
        self.assertError(findings, "unexpected element <other> inside <if>", "Main/body[0]/if")

    def test_missing_required_attribute(self):
        findings = lint_string(program('<assign variable="x"/>'))
        self.assertError(findings, "missing required attribute 'expression'", "Main/body[0]/assign")
        findings = lint_string(program('<declare name="x" type="Integer"/>'))
        self.assertError(findings, "missing required attribute 'array'", "Main/body[0]/declare")
        self.assertError(findings, "missing required attribute 'size'", "Main/body[0]/declare")

    def test_unknown_attribute_is_warning(self):
        findings = lint_string(program('<output expression="1" colour="red"/>'))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "unknown attribute 'colour'", "Main/body[0]/output")

    def test_statement_path_format(self):
        body = """
            <declare name="x" type="Integer" array="False" size=""/>
            <input variable="x"/>
            <output expression="x"/>
            <if expression="x &gt; 1">
                <then>
                    <output expression="y"/>
                </then>
                <else/>
            </if>
        """
        findings = lint_string(program(body))
        self.assertError(findings, "undeclared variable 'y'", "Main/body[3]/if/then[0]/output")

    def test_missing_attributes_section_is_warning(self):
        src = ('<flowgorithm fileversion="3.0"><function name="Main" type="None" variable="">'
               '<parameters/><body/></function></flowgorithm>')
        findings = lint_string(src)
        self.assertNoErrors(findings)
        self.assertWarning(findings, "no <attributes> element")


class DeclarationErrorsTest(LintTestCase):
    def test_undeclared_variable(self):
        findings = lint_string(program('<output expression="x + 1"/>'))
        self.assertError(findings, "undeclared variable 'x'", "Main/body[0]/output")

    def test_use_before_declaration_has_hint(self):
        body = ('<output expression="x"/>\n'
                '<declare name="x" type="Integer" array="False" size=""/>')
        findings = lint_string(program(body))
        self.assertError(findings, "declared later in the function", "Main/body[0]/output")

    def test_undeclared_assign_input_and_for_targets(self):
        findings = lint_string(program('<assign variable="x" expression="1"/>'))
        self.assertError(findings, "undeclared variable 'x'", "Main/body[0]/assign")
        findings = lint_string(program('<input variable="arr[0]"/>'))
        self.assertError(findings, "undeclared variable 'arr'", "Main/body[0]/input")
        findings = lint_string(program('<for variable="i" start="0" end="1" step="1"/>'))
        self.assertError(findings, "undeclared variable 'i'", "Main/body[0]/for")

    def test_duplicate_declaration(self):
        body = ('<declare name="x" type="Integer" array="False" size=""/>\n'
                '<declare name="X" type="Real" array="False" size=""/>')
        findings = lint_string(program(body))
        self.assertError(findings, "duplicate declaration of 'X'", "Main/body[1]/declare")

    def test_duplicate_within_one_declare_and_empty_name(self):
        findings = lint_string(program('<declare name="a, a, " type="Integer" array="False" size=""/>'))
        self.assertError(findings, "duplicate declaration of 'a'")
        self.assertError(findings, "empty name in declare list")

    def test_duplicates_in_sequential_ifs_are_errors(self):
        body = """
            <if expression="true"><then><declare name="x" type="Integer" array="False" size=""/></then><else/></if>
            <if expression="true"><then><declare name="x" type="Integer" array="False" size=""/></then><else/></if>
        """
        findings = lint_string(program(body))
        self.assertError(findings, "duplicate declaration of 'x'", "Main/body[1]/if/then[0]/declare")

    def test_redeclaring_a_parameter(self):
        functions = ('<function name="F" type="None" variable="">'
                     '<parameters><parameter name="p" type="Integer" array="False"/></parameters>'
                     '<body><declare name="p" type="Integer" array="False" size=""/></body></function>')
        findings = lint_string(program('<call expression="F(1)"/>', functions))
        self.assertError(findings, "'p' is already declared as a parameter", "F/body[0]/declare")

    def test_identifier_with_underscore(self):
        findings = lint_string(program('<declare name="my_var" type="Integer" array="False" size=""/>'))
        self.assertError(findings, "underscores are not allowed", "Main/body[0]/declare")
        functions = ('<function name="do_it" type="None" variable=""><parameters>'
                     '<parameter name="a_b" type="Integer" array="False"/></parameters><body/></function>')
        findings = lint_string(program('<output expression="1"/>', functions))
        self.assertError(findings, "illegal identifier 'do_it'", "do_it")
        self.assertError(findings, "illegal identifier 'a_b'", "do_it/parameters[0]")

    def test_identifier_starting_with_digit(self):
        findings = lint_string(program('<declare name="1st" type="Integer" array="False" size=""/>'))
        self.assertError(findings, "illegal identifier '1st'")

    def test_reserved_word_as_identifier(self):
        for word in ("pi", "Len", "Integer", "and", "Cosh", "mod", "Size"):
            findings = lint_string(program(f'<declare name="{word}" type="Integer" array="False" size=""/>'))
            self.assertError(findings, f"'{word}' is a reserved word", "Main/body[0]/declare")
        functions = '<function name="Sqrt" type="None" variable=""><parameters/><body/></function>'
        self.assertError(lint_string(program('<output expression="1"/>', functions)), "reserved word", "Sqrt")

    def test_declare_type_and_array_attributes(self):
        findings = lint_string(program('<declare name="x" type="None" array="False" size=""/>'))
        self.assertError(findings, "declared type cannot be None")
        findings = lint_string(program('<declare name="x" type="Number" array="False" size=""/>'))
        self.assertError(findings, "declared type 'Number' is not one of")
        findings = lint_string(program('<declare name="x" type="Integer" array="yes" size=""/>'))
        self.assertError(findings, "'array' must be True or False")
        findings = lint_string(program('<declare name="x" type="Integer" array="True" size=""/>'))
        self.assertError(findings, "array declaration requires a non-empty 'size'")
        findings = lint_string(program('<declare name="x" type="Integer" array="False" size="5"/>'))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "'array' is False")

    def test_declare_inside_block_is_warning(self):
        body = ('<while expression="true">\n<declare name="x" type="Integer" array="False" size=""/>\n</while>')
        findings = lint_string(program(body))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "declared inside a block", "Main/body[0]/while[0]/declare")

    def test_indexing_a_scalar(self):
        body = ('<declare name="x" type="Integer" array="False" size=""/>\n<output expression="x[0]"/>\n'
                '<assign variable="x[1]" expression="2"/>')
        findings = lint_string(program(body))
        self.assertError(findings, "not an array", "Main/body[1]/output")
        self.assertError(findings, "not an array", "Main/body[2]/assign")

    def test_parameter_checks(self):
        functions = ('<function name="F" type="None" variable=""><parameters>'
                     '<parameter name="a" type="None" array="False"/>'
                     '<parameter name="a" type="Integer" array="maybe"/>'
                     '<parameter type="Integer" array="False"/>'
                     '</parameters><body/></function>')
        findings = lint_string(program('<call expression="F(1, 2, 3)"/>', functions))
        self.assertError(findings, "parameter type cannot be None", "F/parameters[0]")
        self.assertError(findings, "duplicate parameter name 'a'", "F/parameters[1]")
        self.assertError(findings, "'array' must be True or False", "F/parameters[1]")
        self.assertError(findings, "missing required attribute 'name'", "F/parameters[2]")


class ExpressionErrorsTest(LintTestCase):
    def test_syntax_error_reports_expression_and_column(self):
        body = '<declare name="x" type="Integer" array="False" size=""/>\n<output expression="x + * 2"/>'
        findings = lint_string(program(body))
        f = self.assertError(findings, "syntax error", "Main/body[1]/output")
        self.assertIn("'x + * 2'", f.message)
        self.assertIn("column 5", f.message)

    def test_empty_expression(self):
        self.assertError(lint_string(program('<output expression=""/>')), "empty expression")
        self.assertError(lint_string(program('<if expression=" "><then/><else/></if>')), "empty condition")

    def test_string_literal_with_plus(self):
        body = '<declare name="n" type="Integer" array="False" size=""/>\n<output expression="&quot;n=&quot; + n"/>'
        findings = lint_string(program(body))
        self.assertError(findings, "'+' with a string literal operand", "Main/body[1]/output")

    def test_string_variable_with_plus_is_warning(self):
        body = ('<declare name="s" type="String" array="False" size=""/>\n'
                '<output expression="s + 1"/>')
        findings = lint_string(program(body))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "'+' with a String operand", "Main/body[1]/output")

    def test_wrong_intrinsic_arity(self):
        body = ('<declare name="s" type="String" array="False" size=""/>\n'
                '<output expression="Char(s)"/>\n'
                '<output expression="Len(s, 1)"/>\n'
                '<output expression="EOF(1)"/>\n'
                '<output expression="ToFixed(1.5)"/>')
        findings = lint_string(program(body))
        self.assertError(findings, "Char() takes 2 arguments, got 1", "Main/body[1]/output")
        self.assertError(findings, "Len() takes 1 argument, got 2", "Main/body[2]/output")
        self.assertError(findings, "EOF() takes 0 arguments, got 1", "Main/body[3]/output")
        self.assertError(findings, "ToFixed() takes 2 arguments, got 1", "Main/body[4]/output")

    def test_unknown_function(self):
        findings = lint_string(program('<output expression="Foo(1)"/>'))
        self.assertError(findings, "unknown function 'Foo'", "Main/body[0]/output")
        body = '<declare name="x" type="Integer" array="False" size=""/>\n<output expression="x(1)"/>'
        self.assertError(lint_string(program(body)), "'x' is a variable, not a function")

    def test_user_function_arity_and_none_in_expression(self):
        functions = ('<function name="Add" type="Integer" variable="r"><parameters>'
                     '<parameter name="a" type="Integer" array="False"/>'
                     '<parameter name="b" type="Integer" array="False"/></parameters>'
                     '<body><declare name="r" type="Integer" array="False" size=""/>'
                     '<assign variable="r" expression="a + b"/></body></function>'
                     '<function name="Show" type="None" variable=""><parameters/><body/></function>')
        body = '<output expression="Add(1)"/>\n<output expression="Show()"/>'
        findings = lint_string(program(body, functions))
        self.assertError(findings, "function 'Add' takes 2 parameters, got 1", "Main/body[0]/output")
        self.assertError(findings, "has type None (no return value)", "Main/body[1]/output")

    def test_bare_function_name_hint(self):
        functions = '<function name="Show" type="None" variable=""><parameters/><body/></function>'
        findings = lint_string(program('<output expression="Show"/>', functions))
        self.assertError(findings, "'Show' is a function; call it with parentheses")

    def test_target_must_be_variable_or_element(self):
        body = '<declare name="x" type="Integer" array="False" size=""/>\n<assign variable="x + 1" expression="2"/>'
        self.assertError(lint_string(program(body)), "must be a variable name or an array element")
        self.assertError(lint_string(program('<assign variable="3" expression="2"/>')),
                         "must be a variable name or an array element")

    def test_two_dimensional_index_is_error(self):
        body = '<declare name="a" type="Integer" array="True" size="4"/>\n<output expression="a[1, 2]"/>'
        self.assertError(lint_string(program(body)), "one-dimensional")

    def test_precedence_warnings(self):
        body = ('<declare name="x, y" type="Integer" array="False" size=""/>\n'
                '<output expression="-x ^ 2"/>\n'
                '<output expression="0 &lt; x &lt; y"/>\n'
                '<output expression="x / 0"/>')
        findings = lint_string(program(body))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "unary minus binds tighter", "Main/body[1]/output")
        self.assertWarning(findings, "chained comparison", "Main/body[2]/output")
        self.assertWarning(findings, "division by zero", "Main/body[3]/output")

    def test_type_warnings(self):
        body = ('<declare name="n" type="Integer" array="False" size=""/>\n'
                '<declare name="s" type="String" array="False" size=""/>\n'
                '<declare name="b" type="Boolean" array="False" size=""/>\n'
                '<assign variable="n" expression="s"/>\n'
                '<if expression="n"><then/><else/></if>\n'
                '<output expression="b * 2"/>\n'
                '<output expression="n and b"/>\n'
                '<output expression="Len(n)"/>')
        findings = lint_string(program(body))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "assigning String to 'n' which is Integer", "Main/body[3]/assign")
        self.assertWarning(findings, "is Integer; expected Boolean", "Main/body[4]/if")
        self.assertWarning(findings, "operand of '*' is Boolean", "Main/body[5]/output")
        self.assertWarning(findings, "operand of 'and' is Integer", "Main/body[6]/output")
        self.assertWarning(findings, "argument 1 of Len() is Integer; expected a String", "Main/body[7]/output")

    def test_real_to_integer_and_integer_to_real_are_silent(self):
        body = ('<declare name="n" type="Integer" array="False" size=""/>\n'
                '<declare name="r" type="Real" array="False" size=""/>\n'
                '<assign variable="n" expression="r / 2"/>\n'
                '<assign variable="r" expression="n"/>')
        self.assertClean(lint_string(program(body)))


class CallAndForTest(LintTestCase):
    def test_call_must_be_user_function(self):
        body = ('<declare name="x" type="Real" array="False" size=""/>\n'
                '<call expression="Abs(x)"/>\n'
                '<call expression="x + 1"/>\n'
                '<call expression="Nope()"/>')
        findings = lint_string(program(body))
        self.assertError(findings, "'Abs' is an intrinsic function", "Main/body[1]/call")
        self.assertError(findings, "must be a function call", "Main/body[2]/call")
        self.assertError(findings, "unknown function 'Nope'", "Main/body[3]/call")

    def test_call_of_value_returning_function_is_warning(self):
        functions = ('<function name="One" type="Integer" variable="r"><parameters/>'
                     '<body><declare name="r" type="Integer" array="False" size=""/>'
                     '<assign variable="r" expression="1"/></body></function>')
        findings = lint_string(program('<call expression="One()"/>', functions))
        self.assertNoErrors(findings)
        self.assertWarning(findings, "call discards the Integer value", "Main/body[0]/call")

    def test_bad_for_direction(self):
        body = ('<declare name="i" type="Integer" array="False" size=""/>\n'
                '<for variable="i" start="1" end="10" direction="up" step="1"/>')
        findings = lint_string(program(body))
        self.assertError(findings, "'direction' must be 'inc' or 'dec', not 'up'", "Main/body[1]/for")

    def test_for_step_must_be_positive(self):
        body = ('<declare name="i" type="Integer" array="False" size=""/>\n'
                '<for variable="i" start="10" end="1" direction="dec" step="-1"/>\n'
                '<for variable="i" start="1" end="10" direction="inc" step="0"/>')
        findings = lint_string(program(body))
        self.assertError(findings, "'step' must be positive", "Main/body[1]/for")
        self.assertError(findings, "'step' must be a positive number", "Main/body[2]/for")

    def test_for_variable_types(self):
        body = ('<declare name="r" type="Real" array="False" size=""/>\n'
                '<declare name="s" type="String" array="False" size=""/>\n'
                '<declare name="a" type="Integer" array="True" size="3"/>\n'
                '<for variable="r" start="1" end="10" step="1"/>\n'
                '<for variable="s" start="1" end="10" step="1"/>\n'
                '<for variable="a" start="1" end="10" step="1"/>\n'
                '<for variable="a[0]" start="1" end="10" step="1"/>')
        findings = lint_string(program(body))
        self.assertWarning(findings, "loop variable 'r' is Real", "Main/body[3]/for")
        self.assertError(findings, "loop variable 's' is String", "Main/body[4]/for")
        self.assertError(findings, "loop variable 'a' is an array", "Main/body[5]/for")
        self.assertEqual([f for f in errors(findings) if f.path == "Main/body[6]/for"], [])

    def test_output_newline_values(self):
        findings = lint_string(program('<output expression="1" newline="yes"/>'))
        self.assertError(findings, "'newline' must be True or False")


# ---------------------------------------------------------------------------
# Expression parser unit tests
# ---------------------------------------------------------------------------

class ParserTest(unittest.TestCase):
    def parse(self, text):
        return Parser(text).parse()

    def test_precedence(self):
        node = self.parse("a or b and c = d & e + f * g ^ -h")
        self.assertEqual(node.op, "or")
        self.assertEqual(node.right.op, "and")
        self.assertEqual(node.right.right.op, "==")
        self.assertEqual(node.right.right.right.op, "&")
        self.assertEqual(node.right.right.right.right.op, "+")
        self.assertEqual(node.right.right.right.right.right.op, "*")
        self.assertEqual(node.right.right.right.right.right.right.op, "^")
        self.assertEqual(node.right.right.right.right.right.right.right.op, "neg")

    def test_unicode_and_basic_spellings_are_canonical(self):
        for text, op in (("a ≠ b", "!="), ("a <> b", "!="), ("a ≤ b", "<="), ("a ≥ b", ">="), ("a × b", "*"),
                         ("a ÷ b", "/"), ("a ∧ b", "and"), ("a && b", "and"), ("a ∨ b", "or"), ("a || b", "or"),
                         ("a ↑ b", "^"), ("a mod b", "%"), ("a = b", "==")):
            self.assertEqual(self.parse(text).op, op, text)
        self.assertEqual(self.parse("¬a").op, "not")
        self.assertEqual(self.parse("!a").op, "not")
        self.assertEqual(self.parse("π").name, "pi")

    def test_literals(self):
        self.assertFalse(self.parse("42").is_real)
        self.assertTrue(self.parse("3.14").is_real)
        self.assertTrue(self.parse("1e5").is_real)
        self.assertEqual(self.parse('"a b"').text, "a b")

    def test_syntax_errors_carry_positions(self):
        for text, col in (("a +", 4), ("a_b", 1), ("1.", 1), ('"abc', 1), ("a b", 3), ("f(a,)", 5), ("+a", 1),
                          ("a[1][2]", 5), ("x.y", 2)):
            with self.assertRaises(ExprError, msg=text) as cm:
                self.parse(text)
            self.assertEqual(cm.exception.pos + 1, col, text)

    def test_whitespace_including_crlf(self):
        node = self.parse('Len(s) > 0\r\n  && (Char(s, 0) == "y")')
        self.assertEqual(node.op, "and")


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

class MainTest(unittest.TestCase):
    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fprg_lint.main(list(args))
        return code, out.getvalue()

    def test_exit_codes_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.fprg")
            bad = os.path.join(tmp, "bad.fprg")
            with open(good, "w") as fh:
                fh.write(program('<output expression="1"/>'))
            with open(bad, "w") as fh:
                fh.write(program('<output expression="x"/>'))
            code, out = self.run_main(good)
            self.assertEqual(code, 0)
            self.assertIn(f"{good}: 0 errors, 0 warnings", out)
            code, out = self.run_main(good, bad)
            self.assertEqual(code, 1)
            self.assertIn(f"{bad}: Main/body[0]/output: ERROR: undeclared variable 'x'", out)
            self.assertIn(f"{bad}: 1 error, 0 warnings", out)
            self.assertIn("2 files checked, 1 with errors", out)

    def test_strict_and_quiet(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "warn.fprg")
            with open(path, "w") as fh:
                fh.write(program('<output expression="1" extra="1"/>'))
            code, out = self.run_main(path)
            self.assertEqual(code, 0)
            self.assertIn("WARNING: unknown attribute 'extra'", out)
            code, out = self.run_main("--quiet", path)
            self.assertEqual(code, 0)
            self.assertEqual(out, "")
            code, out = self.run_main("--strict", path)
            self.assertEqual(code, 1)
            self.assertIn("ERROR: unknown attribute 'extra'", out)
            self.assertIn("1 error, 0 warnings", out)

    def test_finding_str(self):
        self.assertEqual(str(Finding(ERROR, "Main/body[0]/output", "boom", "f.fprg")),
                         "f.fprg: Main/body[0]/output: ERROR: boom")
        self.assertEqual(str(Finding(WARNING, "", "hmm", "f.fprg")), "f.fprg: WARNING: hmm")


if __name__ == "__main__":
    unittest.main()
