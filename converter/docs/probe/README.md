# Probing Flowgorithm's run-time rules

Flowgorithm documents its shapes and functions but not every run-time rule, and it runs only on
Windows. The flowgorithm library, `fprg_run.py` and the converter's warnings rest on guesses for
the rules below. These four flowcharts settle them: open each one in Flowgorithm, run it, and
compare the console with [`expected.txt`](expected.txt), which is what the library and
`fprg_run.py` assume. A line that differs shows which guess to change (in
`library/src/flowgorithm.py` and `converter/src/fprg_run.py` together, so they keep agreeing).

* `probe.fprg` — nothing in it should stop.
* `probe-array-start.fprg`, `probe-redeclare.fprg`, `probe-overflow.fprg` — each may stop with an
  error; then the error message is the answer.

Regenerate them with `python3 converter/docs/probe/make_probe.py`.

## Answers so far

Flowgorithm from flowgorithm.org's "Executable Only" download, run under Wine Staging 11.21 with
Wine Mono 11.3 on macOS (so on Mono, not Microsoft's .NET):

* `ToFixed(2.5, 0)` stops the program: "Illegal Value — The value '0' is not valid for the
  function ToFixed." `ToFixed` needs at least 1 digit after the point; the library, `fprg_run`
  and the converter now say so. (Line B2 used to be that call; it now tests a negative half.)

| Lines | Question | Assumed now | Otherwise |
|---|---|---|---|
| A1–A3, A7 | how a Real that does not end is written | all the digits Python has (`2.3333333333333335`) | 15 digits (`2.33333333333333`) |
| A4, A5 | when an exponent is used | from 1E+15 on (`1E+15`) | later or never |
| B1–B3 | `ToFixed` of a value exactly halfway | to even (`2.2`, `-2.2`, `0.12`) | away from zero (`2.3`, `-2.3`, `0.13`) |
| B4, B5 | `ToFixed` of 2.675 and 1.005 (just below halfway in binary) | `2.67`, `1.00` | `2.68`, `1.01` (rounds the decimal text) |
| C1–C3 | `%` with negative numbers | sign of the left side (`-1`, `1`, `-1.5`) | Python's (`1`, `-1`, `0.5`) |
| D1 | `2 ^ 3 ^ 2` | left to right (`64`) | right to left (`512`) |
| D2, D3 | `-2 ^ 2`, `2 ^ -1` | `4` (the sign binds first, as documented), `0.5` | `-4` |
| E1–E4 | ordering Strings | by character code (`true false true false`) | dictionary order (`false true ...`) |
| F1, F2 and the line before | Booleans as text | `true` | `True` |
| G1, G2 | do `and` / `or` skip their right side? | yes: no `Probe(...) was evaluated` line | the Probe line appears |
| H1, H3 | the For counter after the loop | one step past the end (`4`, `0`) | the last value (`3`, `1`) |
| H2 | a For end that changes inside the loop | fixed when the loop starts (`3` rounds) | checked again (`2` rounds) |
| I1–I3 | cutting off fractions: `Int(-3.7)`, a Real into an Integer | toward zero (`-3`, `-3`, `3`) | down or rounded (`-4`, `-4`, `4`) |
| I4, I5 | `ToInteger("  42 ")`, `Sgn(-0.5)` | `42`, `-1` | an error |
| J1–J4 | what a new array holds | `0`, `0`, `[]`, `false` | an error: no value yet |
| K1, K2 | a Declare that runs again (in a loop) | a new array (`0`) | the old one (`5`), or an error |
| L1–L3 | how big an Integer gets | no limit | `-2147483648` or an error (32 bits); L3 wraps or stops (64 bits) |
