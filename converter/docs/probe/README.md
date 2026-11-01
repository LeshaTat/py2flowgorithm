# Probing Flowgorithm's run-time rules

Flowgorithm documents its shapes and functions but not every run-time rule, and it runs only on
Windows. The flowgorithm library, `fprg_run.py` and the converter's warnings rest on guesses for
the rules below. Four flowcharts settle them, run in Flowgorithm one file at a time:

* `probe.fprg` — lines A to I;
* `probe-array-start.fprg` — J: what a new array holds;
* `probe-redeclare.fprg` — K: a Declare that runs again;
* `probe-overflow.fprg` — L: how big an Integer gets.

Flowgorithm stops at the first error, and the error message is the answer for that line. Each
answer is recorded below, the library (`library/src/flowgorithm.py`) and `converter/src/fprg_run.py`
are changed to match, and the line is dropped from the probe (or replaced) for the next run.
Once a file runs to `Z end`, its console (the window with the program's output) is compared with
[`expected.txt`](expected.txt), which is what the library and `fprg_run.py` assume now, and the
next file follows.

Regenerate the files with `python3 converter/docs/probe/make_probe.py`.

| Lines | Question | Assumed now | Otherwise |
|---|---|---|---|
| A1–A7 | how a Real is written | 15 significant digits (`2.33333333333333`, `0.3`), an exponent from `1E+15` and below `0.0001` | — (answered) |
| A8–A10 | does Flowgorithm round Reals to 15 digits while calculating (A6 gave `0.999999999999999`)? | no: IEEE doubles (`false`, `5.55111512312578E-17`, `1`) | yes: `true`, `0`, `0.999999999999999` |
| B1–B5 | `ToFixed` rounding | 15 digits, then half away from zero (`2.3`, `-2.3`, `0.13`, `2.68`, `1.01`) | — (answered) |
| C3 | `7.5 % 2` | `1.5` | — (answered) |
| D1–D3 | `2 ^ 3 ^ 2`, `-2 ^ 2`, `2 ^ -1` | `64`, `4`, `0.5` | — (answered) |
| E1–E4 | ordering Strings | by character code (`true false true false`) | answered under Wine; Windows may differ |
| F1, F2 and the line before | a Boolean in Output, in `&`, in `ToString` | `true` | — (answered) |
| G1, G2 | do `and` / `or` skip their right side? | no: both `Probe(...) was evaluated` lines appear | — (answered) |
| H1–H3 | the For counter after the loop; an end that changes inside | `4`, `2` rounds, `0` | — (answered) |
| I1–I5 | `Int`, a Real into an Integer, `ToInteger("  42 ")`, `Sgn` | `-3`, `-3`, `3`, `42`, `-1` | — (answered) |
| J1–J4 | what a new array holds (`probe-array-start.fprg`) | `0`, `0`, `[]`, `false` | an error: no value yet |
| K1, K2 | a Declare that runs again (`probe-redeclare.fprg`) | a new array (`0`) | the old one (`5`), or an error |
| L1–L3 | how big an Integer gets (`probe-overflow.fprg`) | no limit | L1 `-2147483648` or an error (32 bits); L3 wraps or stops (64 bits) |

## Answers so far

Flowgorithm from flowgorithm.org's "Executable Only" download (built for .NET Framework 4.7.2), run
under Wine Staging 11.21 with Wine Mono 11.3 on macOS — so on Mono, not Microsoft's .NET:

* B2 was `ToFixed(2.5, 0)`: it stops the program with "Illegal Value — The value '0' is not valid
  for the function ToFixed." `ToFixed` needs at least 1 digit after the point; the library,
  `fprg_run` and the converter now say so. B2 now tests a negative half.
* C1 was `-7 % 2`: it stops the program with "Illegal Value — The value '-7' is not valid for the
  function % mod." `fprg_run` now stops too, and the converter rejects a negative left side
  written out; Python's own `%` cannot be changed, so the converter's README warns about
  variables. C1 is left out.
* C2 was `7 % -2`: it stops the program the same way ("The value '-2' is not valid for the
  function % mod"), so `%` needs 0 or more on both sides; `fprg_run`, the converter and its README
  follow. C2 is left out.
* The first complete run of `probe.fprg` (2026-11-01) printed:
  * A1–A3 `2.33333333333333`, `0.3`, `0.666666666666667`: Reals show 15 significant digits, as
    .NET Framework prints them (the library printed Python's 17). A4, A5, A7 as assumed.
  * A6 `0.999999999999999` for `1 / 3 * 3`: not a formatting question, since one step below 1.0
    still prints as `1` with 15 digits. Flowgorithm.exe is an any-CPU .NET program (runs 64-bit,
    plain IEEE arithmetic under Wine), so it most likely rounds Reals to 15 digits while
    calculating; A8–A10 check that.
  * B1–B5 `2.3`, `-2.3`, `0.13`, `2.68`, `1.01`: `ToFixed` takes the number to 15 digits and
    rounds half away from zero (the library rounded the binary value half to even).
  * C3 `1.5`; D1–D3 `64`, `4`, `0.5`; E1–E4 by character code; F lines `true` (also
    `ToString(5 > 3)`, which the library used to refuse); H1 `4`, H3 `0`; I1–I5 as assumed.
  * G1, G2: both `Probe(...) was evaluated` lines appeared: `and` / `or` always evaluate both
    sides. `fprg_run` now does too, and the converter's warning says so.
  * H2 `2`: a For loop checks its end again every round. `fprg_run` now does too; the dialect
    already forbids changing the end inside the loop.
  The library and `fprg_run` now print Reals, round in `ToFixed` and accept `ToString(true)` as
  Flowgorithm does.
