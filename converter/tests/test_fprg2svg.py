"""Tests for fprg2svg (Flowgorithm .fprg -> Graphviz DOT/SVG renderer).

Run with::

    python3 -m unittest tests.test_fprg2svg -v

Tests that need the Graphviz ``dot`` executable are skipped when it cannot be
found.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fprg2svg  # noqa: E402

DOT_BIN = fprg2svg.find_dot()

# An if nested inside a while, plus a call to a second function.
SAMPLE = """<?xml version="1.0"?>
<flowgorithm fileversion="3.0">
    <attributes>
        <attribute name="name" value="Even or odd"/>
    </attributes>
    <function name="Main" type="None" variable="">
        <parameters/>
        <body>
            <declare name="n, i" type="Integer" array="False" size=""/>
            <assign variable="i" expression="0"/>
            <input variable="n"/>
            <while expression="i &lt; n">
                <if expression="i % 2 == 0">
                    <then>
                        <output expression="&quot;even &quot; &amp; i" newline="True"/>
                    </then>
                    <else>
                        <output expression="&quot;odd&quot;" newline="True"/>
                    </else>
                </if>
                <assign variable="i" expression="i + 1"/>
            </while>
            <call expression="Done(n)"/>
        </body>
    </function>
    <function name="Done" type="None" variable="">
        <parameters>
            <parameter name="count" type="Integer" array="False"/>
        </parameters>
        <body>
            <output expression="&quot;done &quot; &amp; count" newline="True"/>
        </body>
    </function>
</flowgorithm>
"""


def wrap_body(body: str, extra_functions: str = "") -> str:
    return (
        '<?xml version="1.0"?><flowgorithm fileversion="3.0"><attributes/>'
        '<function name="Main" type="None" variable=""><parameters/><body>'
        + body + "</body></function>" + extra_functions + "</flowgorithm>"
    )


class DotTextTests(unittest.TestCase):
    def setUp(self):
        self.dot = fprg2svg.fprg_to_dot(SAMPLE)

    def test_node_labels(self):
        for label in ('"Main"', '"Declare Integer n, i"', '"i = 0"', '"Input n"', '"i < n"',
                      '"i % 2 == 0"', '"Output \\"even \\" & i"', '"Output \\"odd\\""',
                      '"i = i + 1"', '"End"', '"Done(Integer count)"'):
            self.assertIn(label, self.dot, f"missing label {label}")
        self.assertIn("Call Done(n)", self.dot)  # HTML label of the call node

    def test_shapes(self):
        self.assertIn('shape="hexagon"', self.dot)
        self.assertIn('shape="diamond"', self.dot)
        self.assertIn('shape="parallelogram"', self.dot)
        self.assertIn('peripheries="2"', self.dot)
        self.assertIn("shape=point", self.dot)  # merge / loop-exit points
        self.assertIn("<VR/>", self.dot)  # predefined-process bars of the Call node

    def test_edge_labels_and_sides(self):
        self.assertIn('taillabel="False"', self.dot)
        self.assertIn('taillabel="True"', self.dot)
        # The if's False branch leaves the diamond at the west port, True at the east port.
        false_edges = re.findall(r'(n\d+):w -> n\d+ \[taillabel="False"', self.dot)
        true_edges = re.findall(r'(n\d+):e -> n\d+ \[taillabel="True"', self.dot)
        self.assertTrue(false_edges and true_edges)
        self.assertTrue(set(false_edges) & set(true_edges), "False and True edges share a diamond")
        # Loop: True goes down from the hexagon, the loop-back edge is drawn with dir=back into :e.
        self.assertRegex(self.dot, r'n\d+:s -> n\d+ \[taillabel="True"')
        self.assertRegex(self.dot, r'n\d+:e -> n\d+ \[dir="back"')

    def test_functions_are_clusters_main_first(self):
        clusters = re.findall(r'subgraph cluster_\d+ \{\n\s+label="(\w+)"', self.dot)
        self.assertEqual(clusters, ["Main", "Done"])
        swapped = SAMPLE.replace('<function name="Main"', '<function name="ZZZ"') \
                        .replace('<function name="Done"', '<function name="Main"') \
                        .replace('name="ZZZ"', 'name="Done"')
        clusters = re.findall(r'subgraph cluster_\d+ \{\n\s+label="(\w+)"', fprg2svg.fprg_to_dot(swapped))
        self.assertEqual(clusters[0], "Main")

    def test_function_filter(self):
        only = fprg2svg.fprg_to_dot(SAMPLE, function="done")  # case-insensitive
        self.assertIn('"Done(Integer count)"', only)
        self.assertNotIn('"Declare Integer n, i"', only)
        with self.assertRaises(fprg2svg.FprgError):
            fprg2svg.fprg_to_dot(SAMPLE, function="Nope")

    def test_program_title(self):
        self.assertIn('label="Even or odd"; labelloc=t', self.dot)

    def test_unknown_elements_do_not_raise(self):
        dot = fprg2svg.fprg_to_dot(wrap_body('<more/><turtle action="forward"><output expression="x"/></turtle>'))
        self.assertIn('"<more>"', dot)
        self.assertIn('fillcolor="#E0E0E0"', dot)
        self.assertIn('action=\\"forward\\"', dot)

    def test_empty_bodies_and_branches(self):
        dot = fprg2svg.fprg_to_dot(wrap_body(
            '<if expression="c"><then/><else/></if>'
            '<while expression="w"/>'
            '<do expression="d"/>'
            '<for variable="i" start="1" end="3" step="1"/>'))
        self.assertRegex(dot, r'(n\d+):e -> \1:e \[label="True"\]')  # self-loop for empty loop body
        self.assertIn('"for i = 1 to 3 step 1"', dot)

    def test_for_downto_and_old_declare(self):
        dot = fprg2svg.fprg_to_dot(wrap_body(
            '<declare variables="bill" type="Real"/>'
            '<declare name="a" type="Real" array="True" size="n"/>'
            '<for variable="i" start="10" end="1" direction="dec" step="2"><output expression="i"/></for>'))
        self.assertIn('"Declare Real bill"', dot)
        self.assertIn('"Declare Real a[n]"', dot)
        self.assertIn('"for i = 10 downto 1 step 2"', dot)

    def test_return_terminal_and_array_parameter(self):
        func = ('<function name="Area" type="Real" variable="a"><parameters>'
                '<parameter name="r" type="Real" array="False"/>'
                '<parameter name="xs" type="Integer" array="True"/></parameters>'
                '<body><declare name="a" type="Real" array="False" size=""/></body></function>')
        dot = fprg2svg.fprg_to_dot(wrap_body("", func))
        self.assertIn('"Area(Real r, Integer xs[])"', dot)
        self.assertIn('"Return a"', dot)

    def test_comments_and_breakpoints(self):
        dot = fprg2svg.fprg_to_dot(wrap_body(
            '<comment text="hello&#13;&#10;world"/><breakpoint/><output expression="1"/>'))
        self.assertIn('shape="note"', dot)
        self.assertIn("rank=same", dot)
        self.assertIn("style=dashed", dot)
        self.assertIn('"hello\\lworld\\l"', dot)  # CRLF becomes a left-justified line break
        self.assertIn('shape="octagon"', dot)
        self.assertIn('"Breakpoint"', dot)

    def test_comment_before_do_loop_stays_in_outer_cluster(self):
        # The do loop's first body node lives in an invisible cluster; a comment
        # preceding the loop must not drag it out via rank=same (dot warns and
        # breaks the layout otherwise), so it hangs off the hexagon instead.
        dot = fprg2svg.fprg_to_dot(wrap_body(
            '<while expression="w"><comment text="c"/><do expression="d"><input variable="x"/></do></while>'))
        hexagon = re.search(r'(n\d+) \[shape="hexagon".*?label="d"', dot).group(1)
        self.assertRegex(dot, r"rank=same; " + hexagon + r"; n\d+;")
        body_node = re.search(r'(n\d+) \[shape="parallelogram"', dot).group(1)
        self.assertNotRegex(dot, r"rank=same; " + body_node)

    def test_escaping(self):
        dot = fprg2svg.fprg_to_dot(wrap_body(
            '<assign variable="s" expression="&quot;a\\b&quot; &amp; &quot;&lt;x&gt;&quot;"/>'
            '<call expression="F(&quot;q&quot;, 1 &lt; 2 &amp;&amp; 3 &gt; 2)"/>'))
        self.assertIn(r'"s = \"a\\b\" & \"<x>\""', dot)  # backslash and quotes escaped, <>& literal
        self.assertIn("Call F(&quot;q&quot;, 1 &lt; 2 &amp;&amp; 3 &gt; 2)", dot)  # HTML label escaped

    def test_wrap_keeps_text_verbatim(self):
        long = "Output " + " ".join(f"word{i}" for i in range(30))
        dot = fprg2svg.fprg_to_dot(wrap_body(f'<output expression="{long[7:]}"/>'))
        self.assertIn("\\l", dot)
        joined = " ".join(re.search(r'"(Output word0.*?)"', dot, re.S).group(1).split("\\l"))
        self.assertEqual(joined.split(), long.split())
        unwrapped = fprg2svg.fprg_to_dot(wrap_body(f'<output expression="{long[7:]}"/>'), wrap=0)
        self.assertIn(f'"{long}"', unwrapped)

    def test_bad_input(self):
        with self.assertRaises(fprg2svg.FprgError):
            fprg2svg.fprg_to_dot("<flowgorithm><function")
        with self.assertRaises(fprg2svg.FprgError):
            fprg2svg.fprg_to_dot("<notflowgorithm/>")
        with self.assertRaises(fprg2svg.FprgError):
            fprg2svg.fprg_to_dot("<flowgorithm/>")
        self.assertIn("Main", fprg2svg.fprg_to_dot(SAMPLE.encode("ascii")))  # bytes accepted too


@unittest.skipUnless(DOT_BIN, "Graphviz dot not found")
class DotRenderTests(unittest.TestCase):
    def positions(self, dot_text):
        plain = subprocess.run([DOT_BIN, "-Tplain"], input=dot_text.encode(), capture_output=True, check=True)
        pos = {}
        for line in plain.stdout.decode().splitlines():
            parts = line.split()
            if parts and parts[0] == "node":
                pos[parts[1]] = (float(parts[2]), float(parts[3]))
        return pos

    def test_dot_accepts_output_and_sides_are_right(self):
        dot_text = fprg2svg.fprg_to_dot(SAMPLE)
        pos = self.positions(dot_text)
        false_head = re.search(r'n\d+:w -> (n\d+) \[taillabel="False"', dot_text).group(1)
        true_head = re.search(r'n\d+:e -> (n\d+) \[taillabel="True"', dot_text).group(1)
        self.assertLess(pos[false_head][0], pos[true_head][0], "False branch must be left of True branch")

    def test_cli_renders_svg_and_dot(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "sample.fprg")
            with open(src, "w", encoding="ascii") as fh:
                fh.write(SAMPLE)
            self.assertEqual(fprg2svg.main([src]), 0)
            with open(os.path.join(tmp, "sample.svg"), encoding="utf-8") as fh:
                self.assertIn("<svg", fh.read())
            out = os.path.join(tmp, "done.dot")
            self.assertEqual(fprg2svg.main([src, "-o", out, "--function", "Done"]), 0)
            with open(out, encoding="utf-8") as fh:
                self.assertIn('"Done(Integer count)"', fh.read())
            self.assertEqual(fprg2svg.main([src, "--function", "Missing"]), 1)
            self.assertEqual(fprg2svg.main([src, "-o", os.path.join(tmp, "x.png"),
                                            "--dot-bin", os.path.join(tmp, "no-such-dot")]), 2)


if __name__ == "__main__":
    unittest.main()
