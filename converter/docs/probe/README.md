# Probing Flowgorithm's run-time rules

Flowgorithm documents its shapes and functions but not every run-time rule, and it runs only on
Windows. The flowgorithm library, `fprg_run.py` and the converter's warnings rest on guesses for
the rules below. `probe.fprg` settles them: open it in Flowgorithm and run it.

Flowgorithm stops at the first error, and the error message is the answer for that line. Each
answer is recorded below, the library (`library/src/flowgorithm.py`) and `converter/src/fprg_run.py`
are changed to match, and the line is dropped from the probe (or replaced) for the next run.
Once the probe runs to `Z end`, its console (the window with the program's output) is compared
with [`expected.txt`](expected.txt), which is what the library and `fprg_run.py` assume now.

Regenerate the files with `python3 converter/docs/probe/make_probe.py`.

| Lines | Question | Assumed now | Otherwise |
|---|---|---|---|
| A1–A3, A7 | how a Real that does not end is written | all the digits Python has (`2.3333333333333335`) | 15 digits (`2.33333333333333`), as .NET Framework does |
| A4, A5 | when an exponent is used | from 1E+15 on (`1E+15`) | later or never |
| B1–B3 | `ToFixed` of a value exactly halfway | to even (`2.2`, `-2.2`, `0.12`) | away from zero (`2.3`, `-2.3`, `0.13`) |
| B4, B5 | `ToFixed` of 2.675 and 1.005 (just below halfway in binary) | `2.67`, `1.00` | `2.68`, `1.01` (rounds the decimal text) |
| C2, C3 | `7 % -2`, `7.5 % 2` | `1`, `1.5` | `-1`, or an error |
| D1 | `2 ^ 3 ^ 2` | left to right (`64`) | right to left (`512`) |
| D2, D3 | `-2 ^ 2`, `2 ^ -1` | `4` (the sign binds first, as documented), `0.5` | `-4` |
| E1–E4 | ordering Strings | by character code (`true false true false`) | dictionary order (`false true ...`), or an error |
| F1, F2 and the line before | a Boolean in Output, in `&`, in `ToString` | `true` | `True`, or an error |
| G1, G2 | do `and` / `or` skip their right side? | yes: no `Probe(...) was evaluated` line | the Probe line appears |
| H1, H3 | the For counter after the loop | one step past the end (`4`, `0`) | the last value (`3`, `1`) |
| H2 | a For end that changes inside the loop | fixed when the loop starts (`3` rounds) | checked again (`2` rounds) |
| I1–I3 | `Int(-3.7)`; a Real put into an Integer variable | toward zero (`-3`, `-3`, `3`) | down or rounded (`-4`, `-4`, `4`) |
| I4, I5 | `ToInteger("  42 ")`, `Sgn(-0.5)` | `42`, `-1` | an error |
| J1–J4 | what a new array holds | `0`, `0`, `[]`, `false` | an error: no value yet |
| K1, K2 | a Declare that runs again (in a loop) | a new array (`0`) | the old one (`5`), or an error |
| L1–L3 | how big an Integer gets | no limit | L1 `-2147483648` or an error (32 bits); L3 wraps or stops (64 bits) |

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
