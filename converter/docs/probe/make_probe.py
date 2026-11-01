"""Build the probe flowcharts: small programs that show, when run in real Flowgorithm, the run-time
rules py2fprg, the flowgorithm library (library/src/flowgorithm.py) and fprg_run had to guess (see
"What can still differ" in converter/README.md and the "Semantics that had to be guessed" list in
fprg_run.py).

    python3 converter/docs/probe/make_probe.py      # writes the .fprg files and expected.txt here

probe.fprg holds all the checks. Flowgorithm stops at the first error: the error message is the
answer, so the line it stopped at is recorded in README.md, the library and fprg_run follow it, and
the line is dropped or replaced here before the next run, until the probe runs to `Z end`.
Every output line starts with a label (A1, B2, ...); README.md in this folder says what each label
tests. The probes are written as flowcharts directly because the dialect rejects most of these
constructs on purpose.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "src"))

import fprg_run  # noqa: E402
from py2fprg.model import (Assign, BOOLEAN, Declare, For, Function, INTEGER, If, Output, Param,  # noqa: E402
                           Program, REAL, STRING)
from py2fprg.writer import write_program  # noqa: E402


def show(label: str, expression: str) -> Output:
    return Output(f'"{label} " & ({expression})')


def text(line: str) -> Output:
    return Output(f'"{line}"')


def checks() -> list:
    """Every check, in label order. Answered checks that stop Flowgorithm are left out (see README.md)."""
    return [
        Declare(["i", "n", "rounds", "k", "big", "round"], INTEGER),
        Declare(["ok"], BOOLEAN),
        # A: how Reals are written
        show("A1", "7 / 3"), show("A2", "0.1 + 0.2"), show("A3", "2 / 3"), show("A4", "10.0 ^ 15"),
        show("A5", "123456789.0 * 10000000"), show("A6", "1 / 3 * 3"), show("A7", "0.1 * 0.0001"),
        # B: ToFixed on values exactly halfway, and on values just below halfway in binary
        show("B1", "ToFixed(2.25, 1)"), show("B2", "ToFixed(-2.25, 1)"), show("B3", "ToFixed(0.125, 2)"),
        show("B4", "ToFixed(2.675, 2)"), show("B5", "ToFixed(1.005, 2)"),
        # C: % (C1, -7 % 2, stops Flowgorithm)
        show("C2", "7 % -2"), show("C3", "7.5 % 2"),
        # D: ^
        show("D1", "2 ^ 3 ^ 2"), show("D2", "-2 ^ 2"), show("D3", "2 ^ -1"),
        # E: ordering Strings
        show("E1", '"B" < "a"'), show("E2", '"apple" < "Banana"'), show("E3", '"10" < "9"'),
        show("E4", '"a" == "A"'),
        # F: Booleans as text
        Assign("ok", "true"), Output("ok"), show("F1", "ok"), show("F2", "ToString(5 > 3)"),
        # G: is the right side of and / or evaluated when the left side decides?
        text("G1 before"), Assign("ok", "false and Probe(1)"), text("G1 after"),
        text("G2 before"), Assign("ok", "true or Probe(2)"), text("G2 after"),
        # H: the For counter after the loop, and an end that changes inside the loop
        For("i", "1", "3", body=[]), show("H1", "i"),
        Assign("n", "3"), Assign("rounds", "0"),
        For("i", "1", "n", body=[Assign("n", "n - 1"), Assign("rounds", "rounds + 1")]), show("H2", "rounds"),
        For("i", "3", "1", "dec", body=[]), show("H3", "i"),
        # I: whole numbers from Reals and text
        show("I1", "Int(-3.7)"), Assign("k", "-3.7"), show("I2", "k"), Assign("k", "3.7"), show("I3", "k"),
        show("I4", 'ToInteger("  42 ")'), show("I5", "Sgn(-0.5)"),
        # J: what a new array holds
        Declare(["xs"], INTEGER, True, "3"), Declare(["rs"], REAL, True, "2"), Declare(["ss"], STRING, True, "2"),
        Declare(["bs"], BOOLEAN, True, "2"),
        show("J1", "xs[0]"), show("J2", "rs[1]"), show("J3", '"[" & ss[0] & "]"'), show("J4", "bs[1]"),
        # K: a Declare that runs again
        For("round", "1", "2", body=[
            Declare(["row"], INTEGER, True, "2"),
            If("round == 1", [Assign("row[0]", "5"), text("K1 round 1: row[0] set to 5")],
               [show("K2 round 2: row[0] is", "row[0]")])]),
        # L: how big an Integer gets (small literals only: a literal too big could stop the file loading)
        Assign("big", "2147483647"), Assign("big", "big + 1"), show("L1", "big"),
        Assign("big", "big * big"), show("L2", "big"), Assign("big", "big * 2"), show("L3", "big"),
        text("Z end"),
    ]


def probe_function() -> Function:
    """Probe(n): says that it was called, returns true."""
    return Function("Probe", BOOLEAN, "result", [Param("n", INTEGER)], [
        Declare(["result"], BOOLEAN),
        Output('"    Probe(" & n & ") was evaluated"'),
        Assign("result", "true"),
    ])


PROBES = {
    "probe": ("Probe: run-time rules", "Run me in Flowgorithm: an error message, or the console up to Z end.",
              checks(), [probe_function()], [[]]),
}


def main() -> None:
    expected = []
    for name, (title, about, main_body, functions, runs) in PROBES.items():
        program = Program(title, [Function("Main", body=main_body)] + functions, authors="py2fprg", about=about)
        xml = write_program(program, metadata=False)
        with open(os.path.join(HERE, name + ".fprg"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(xml)
        for answers in runs:
            try:
                out = fprg_run.run_string(xml, answers)
            except fprg_run.FprgRuntimeError as e:
                out = f"(stops: {e})\n"
            typed = f" (typed {answers[0]})" if answers else ""
            expected.append(f"== {name}.fprg{typed}\n{out}")
        print(f"wrote {os.path.relpath(os.path.join(HERE, name + '.fprg'))}")
    with open(os.path.join(HERE, "expected.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("What fprg_run (and the flowgorithm library) assume each probe prints.\n\n" + "\n".join(expected))
    print(f"wrote {os.path.relpath(os.path.join(HERE, 'expected.txt'))}")


if __name__ == "__main__":
    main()
