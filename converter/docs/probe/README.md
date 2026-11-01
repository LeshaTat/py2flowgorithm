# Probing Flowgorithm's run-time rules

Flowgorithm documents its shapes and functions but not every run-time rule, and it runs only on
Windows. The flowgorithm library, `fprg_run.py` and the converter's warnings rest on guesses for
the rules below. Four flowcharts settle them, run in Flowgorithm one file at a time:

* `probe.fprg` — lines A to I;
* `probe-array-start.fprg` — J: what a new array holds (and A11);
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
| A8–A10 | does Flowgorithm round Reals to 15 digits while calculating (A6 gave `0.999999999999999`)? | yes: `true`, `0`, `0.999999999999999` | — (answered) |
| A11 | are function results rounded too? (in `probe-array-start.fprg`) | yes: `Sqrt(2) * Sqrt(2)` is `2.00000000000001` | — (answered) |
| B1–B5 | `ToFixed` rounding | 15 digits, then half away from zero (`2.3`, `-2.3`, `0.13`, `2.68`, `1.01`) | — (answered) |
| C3 | `7.5 % 2` | `1.5` | — (answered) |
| D1–D3 | `2 ^ 3 ^ 2`, `-2 ^ 2`, `2 ^ -1` | `64`, `4`, `0.5` | — (answered) |
| E1–E4 | ordering Strings | by character code (`true false true false`) | answered under Wine; Windows may differ |
| F1, F2 and the line before | a Boolean in Output, in `&`, in `ToString` | `true` | — (answered) |
| G1, G2 | do `and` / `or` skip their right side? | no: both `Probe(...) was evaluated` lines appear | — (answered) |
| H1–H3 | the For counter after the loop; an end that changes inside | `4`, `2` rounds, `0` | — (answered) |
| I1–I5 | `Int`, a Real into an Integer, `ToInteger("  42 ")`, `Sgn` | `-3`, `-3`, `3`, `42`, `-1` | — (answered) |
| J1–J5 | arrays (`probe-array-start.fprg`) | filled first as the converter does, they work; an unfilled one stops the program | — (answered) |
| K1, K2 | a Declare that runs again (`probe-redeclare.fprg`) | a new array without values: K2 stops with "not initialized" | — (answered) |
| L1–L3 | how big an Integer gets (`probe-overflow.fprg`) | 64 bits, 15 significant digits in arithmetic: `2147483648`, `4611686018427389952`; L3 overflows | — (answered) |

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
* The second run of `probe.fprg` printed A8 `true`, A9 `0`, A10 `0.999999999999999`: Flowgorithm
  rounds every Real to 15 significant digits while calculating, also when one is stored in a
  variable. `fprg_run` now does the same (for function results too, which A11 checks), and the
  library rounds its own functions' results. Python's arithmetic cannot be rounded, so the
  converter warns about `==` and `!=` between Reals, where the two would decide differently.
* `probe-array-start.fprg` stopped at J1 with "Variable Not Initialized — You attempted to read
  data from a variable before any data was stored into it. The variable 'xs' was not
  initialized." A new array holds no values (and a declared variable none either), while
  Python's `[0] * n` holds zeros. The converter now follows every `[v] * n` with a loop that fills
  the array (left out when the next loop stores into every element first), so any fill value
  works; `fprg_run` stops when an unset variable or element is read. `examples/arith_quiz/quiz.fprg`
  gained such a loop: its `results` array was read where wrong answers had stored nothing.
* A11 printed `2.00000000000001`: function results are rounded to 15 digits too, as assumed.
* The next run passed J1–J4 (arrays of each type filled the way the converter fills them) and stopped at J5, an unfilled String array: "The variable 'empty' was not initialized". J5 is left out.
* `probe-redeclare.fprg` stopped at K2: "The variable 'row' was not initialized". A Declare that runs again makes a new, empty array, as `fprg_run` assumed (the dialect makes arrays outside loops anyway). K2 is left out.
* `probe-overflow.fprg` printed L1 `2147483648` (Integers are 64-bit, not 32) and L2
  `4611686018427389952` for `2147483648 * 2147483648` (2^62 is 4611686018427387904): Integer
  arithmetic keeps 15 significant digits, like Reals. L3 (`big * 2`) stopped with "Overflow — Assign :
  big = 9.22337203685478E+18". `fprg_run` now rounds Integer results the same way and stops when an
  Integer variable gets more than 9223372036854775807. L3 is left out.
