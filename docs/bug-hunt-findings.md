# Adversarial bug hunt — findings and status (2026-10-30)

Source: a 10-finder / dedup / 3-lens-verification workflow run against the converter *before* the
independent review's fixes landed. Its dedup step failed (output too large), so near-duplicates remain,
and the verifiers of the last 64 findings were cut off, so those are unconfirmed leads.

State of the code (2026-10-30): every confirmed finding below is fixed, converted where it used to
be a clean error, or (for real type errors) a clean error. `//` and `%` keep Flowgorithm's
truncation only for values of unknown sign, with a warning. Each
item has a regression test in `tests/test_py2fprg.py` (`BugHuntRegressionTest`, and
`ProjectLayoutTest` for the project-layout leads); 265 tests pass. The unverified leads at the end
were triaged: the ones marked *fixed* there were reproduced first. The "Actual" blocks below show
the output at the time of the hunt, not today's.

Rules that changed while fixing (also in the README):

* `# fg: ignore` is applied by one pre-pass before anything else looks at the code, with the same
  placement rules everywhere: it removes the next statement of its block; on a header line (any line
  up to the `:`) the whole compound statement; on an `elif` line that branch; on an `else:` line the
  else branch. A directive with no statement to apply to gets a warning.
* Annotations are declarations: an `int` annotation never takes a float. Inferred variables,
  parameters and arrays widen from Integer to Real instead, and the function is converted again so
  that earlier uses see the wider type.
* A name assigned anywhere in a function is local there (Python's rule), so it may shadow a module
  constant. A module-level name assigned more than once, or not to a literal, is a variable: reading
  it in a function is a clean error (Flowgorithm has no globals).
* The `if __name__ == "__main__":` block decides the entry point: the function it calls (usually
  `main()`, possibly imported, possibly as `sys.exit(main())`), or the block itself when it does more.
* What an expression needs evaluated first (an `input()` inside an expression, a chained comparison's
  middle call, a Boolean used as a number, ...) goes into a variable just before the statement; for
  a loop condition, before the loop and again at the end of its body.
* A for loop counts with a hidden `<name>Counter` when Flowgorithm's For could not use the Python
  variable itself (assigned in the body, read after the loop, or used as a Real).
* `break`, `continue` and `return` work anywhere in a loop (flags in the loop conditions; a `for`
  with an early exit becomes a While), `for/while ... else` too; `while True: A; if c: break; B`
  becomes a priming read. Conditional expressions, `min`/`max`/`sum`, `in` (literal tuples and
  lists, list variables, `range(a, b)`, one character against a string literal) and loops over
  literals convert as well. A statement whose hoisted part would overtake an earlier call is
  converted again with all its calls in variables, in Python's order.
* String repetition, `upper`/`lower`/`strip`/`isdigit`/`isalpha`/`isupper`/`islower`/`count` and string
  slices become small loops (ASCII); helper variables never take the name of one of the function's
  own variables.

## Confirmed by verification (33)

### C0. Chained comparison evaluates the middle operand twice (random/side effects differ from Python)

- **status:** converted: the middle operand is evaluated once, into a variable, before the statement (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTT, finder: precedence
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py FunctionConverter.e_Compare (the `left = right` loop re-emits the shared operand with self.sub())`
- expected: The middle operand evaluated once: hoist it into a temporary (`<assign variable="temp" expression="1 + Random(10)"/>` then `1 <= temp and temp <= 5`) when it is not a plain variable/literal, or report a clean error for chained comparisons whose middle operand is a call / Random.

```python
import random

def main():
    if 1 <= random.randint(1, 10) <= 5:
        print("low")

if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<if expression="1 <= 1 + Random(10) and 1 + Random(10) <= 5">
    <then>
        <output expression=""low"" newline="True"/>
    </then>
    <else/>
</if>

(Python draws ONE number and tests it against both bounds; the emitted program draws two different numbers, so e.g. draws 1 then 9 fail the test where Python would pass. Same with a user function: `if 2 < roll() < 6:` becomes `2 < roll() and roll() < 6` -- roll() runs twice and its print("rolling") appears twice.)
```

### C1. `//` with a negative operand truncates toward zero (Int(a / b)) while Python floors

- **status:** converted: where an operand may be negative the result gets Python's correction before the statement (exact for every sign combination); non-negative operands and `% ... == 0` stay plain; only values of unknown sign (inputs, parameters) keep the truncation, with a warning (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTF, finder: precedence
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py FunctionConverter.e_BinOp (ast.FloorDiv branch); FunctionConverter.infer (FloorDiv always INTEGER)`
- expected: -4. Either emit a floor-correct expression for integer operands, e.g. `Int((n - (n % 2 + 2) % 2) / 2)` (uses Python-style modulo; checked for all four sign combinations), or at least warn like the existing math.floor warning ("// mapped to Int(a / b), which truncates toward zero for negative operands").

```python
def main():
    n = -7
    print(n // 2)

if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<assign variable="n" expression="-7"/>
<output expression="Int(n / 2)" newline="True"/>

(Int(-3.5) = -3 per docs/fprg-format.md "Int(n) truncates"; Python prints -4. Also `-n // 2` -> `Int(-n / 2)`, `7 % -3`-style cases, and `7.5 // 2` is inferred Integer although Python yields 3.0. No warning is emitted, although math.floor -> Int() and round(x) do get a truncation warning.)
```

### C2. `%` with a negative dividend: emitted `%` follows the dividend's sign, Python's result is non-negative (realistic wrap-around index)

- **status:** converted: where an operand may be negative the result gets Python's correction before the statement (exact for every sign combination); non-negative operands and `% ... == 0` stay plain; only values of unknown sign (inputs, parameters) keep the truncation, with a warning (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTF, finder: precedence
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py FunctionConverter.e_BinOp (ast.Mod branch)`
- expected: 4 for a positive divisor: emit `((i - 1) % n + n) % n` when the dividend is not provably non-negative (or when the operands are not both literals/positive), or emit a warning as for math.floor.

```python
def main():
    n = 5
    i = 0
    prev = (i - 1) % n
    print(prev)

if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<assign variable="prev" expression="(i - 1) % n"/>
<output expression="prev" newline="True"/>

(Python prints 4. Flowgorithm is a C# program and its `%` is C#'s remainder, which takes the sign of the dividend: -1 % 5 = -1, and as an array index that is out of bounds. Likewise `7 % -3` -> Python -2 vs C#-style 1. CAVEAT: docs/fprg-format.md does not state the sign rule of Flowgorithm's `%`; if the author confirms Flowgorithm floors, this finding is void.)
```

### C3. Denormal float literals are silently rewritten to 0.0

- **status:** converted: written as `5 * 10 ^ -300 * 10 ^ -24`; other exponent literals as `1.602176634 * 10 ^ -19` (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: precedence
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py FunctionConverter.float_text and module-level literal_text (used for module constants)`
- expected: The literal's value (a Real is a double, so it is representable) or a clean "file:line: error: literal cannot be written without exponent notation"; never a silent value change. (Large values such as 1.5e300 are expanded to a 301-digit literal, which is at least exact.)

```python
def main():
    x = 5e-324
    print(x)

if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<declare name="x" type="Real" array="False" size=""/>
<assign variable="x" expression="0.0"/>
<output expression="x" newline="True"/>

(Python prints 5e-324; `1e-320` also becomes 0.0. `format(v, ".17f").rstrip("0")` drops every digit below 1e-17, then the empty fraction is turned into "0.0".)
```

### C4. random.randint(lo, hi) with a non-literal lower bound evaluates `lo` twice

- **status:** converted: the lower bound is evaluated once, into a variable, before the statement (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: precedence
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py FunctionConverter.library_call (random.randint / randrange branches) via minus_expr`
- expected: The bound evaluated once -- store `lo` in a temporary when it is not a literal/variable, e.g. `temp = low()` then `temp + Random(10 - temp + 1)`.

```python
import random

def low() -> int:
    print("asking")
    return random.randint(1, 3)

def main():
    r = random.randint(low(), 10)
    print(r)

if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<assign variable="r" expression="low() + Random(10 - low() + 1)"/>

("asking" is printed twice instead of once, and the two draws differ: with low()=3 then low()=1 the result is 3 + Random(10), i.e. up to 12, outside Python's [low, 10]. Same for random.randrange(lo, hi) -> `lo + Random(hi - lo)`.)
```

### C5. A Boolean used as a number (`total += a > b`) is emitted as `total + (a > b)` with no diagnostic

- **status:** converted: `total += a > b` becomes `If a > b: total = total + 1`; other uses of a Boolean as a number get 1/0 from an If (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: precedence
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py FunctionConverter.e_BinOp (arithmetic branches lack a Boolean operand check)`
- expected: A clean "file:line: error: arithmetic on a boolean is not supported (use an if statement)" -- e_BinOp checks operand types for String (`&`, repetition, %-formatting) but not for Boolean.

```python
def main():
    total = 0
    a = 3
    b = 1
    total += a > b
    print(total)

if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<assign variable="total" expression="total + (a > b)"/>
<output expression="total" newline="True"/>

Converter: no warning or error. fprg_lint: "operand of '+' is Boolean; expected a number". Python prints 1 (True == 1); Flowgorithm cannot add a Boolean, so the program fails.
```

### C6. Variable copied from a numeric variable inside a loop keeps the Integer type of the first iteration while the source widens to Real -> truncated values (and wrong inferred return type)

- **status:** fixed: a function is converted again with the final variable types when a variable widened after it was used (`ProgramBuilder.convert_function`; test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: types
- location: `py2fprg/convert.py: assign_to() -> infer(value) + var_assign() record the RHS type as it is at the moment the statement is converted; once `balance` is widened to Real by a later statement nothing revisits `old` (needs a second inference pass / fixpoint over the function body, or a check that no recorded type depends on a variable whose type widened afterwards).`
- expected: `old` declared Real (`<declare name="balance, old" type="Real" .../>`). Python prints: 1000 1050.0 / 1050.0 1102.5 / 1102.5 1157.625.

```python
def main():
    balance = 1000
    for year in range(3):
        old = balance
        balance = balance * 1.05
        print(old, balance)


if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<declare name="balance" type="Real" array="False" size=""/>
<declare name="year, old" type="Integer" array="False" size=""/>
<assign variable="balance" expression="1000"/>
<for variable="year" start="0" end="2" direction="inc" step="1">
    <assign variable="old" expression="balance"/>
    <assign variable="balance" expression="balance * 1.05"/>
    <output expression="old & " " & balance" newline="True"/>
</for>
(`old` is Integer, so Flowgorithm prints old = 1000, 1050, 1102 — Real->Integer truncates.)
Same in while/do loops (`k = 10; while True: last = k; k = k / 4; if k < 1: break` -> `last` Integer prints 2 instead of 2.5), and it corrupts inferred return types: `def f(n: int): total = 0; for i in range(n): half = total; total = total + 0.5; return half` becomes `<function name="f" type="Integer" variable="half">` and f(2) returns 0 instead of 0.5.
```

### C7. Reassigning a parameter with a Real expression keeps the Integer parameter type -> value truncated

- **status:** fixed: an `int`-annotated parameter assigned a float is a clean error (as mypy reports it); an un-annotated parameter widens to Real (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: types
- location: `py2fprg/convert.py: var_assign() joins info.type to Real for a VarInfo with is_param=True, but the Param list was already built in convert() from the annotation and nothing checks `info.is_param` when the type widens.`
- expected: half(5) = 2.5 (Python). Either a clean error ("parameter 'n' is annotated int but is assigned a float; copy it into a new variable") or the assignment redirected into a fresh Real local that replaces `n` from there on.

```python
def half(n: int) -> float:
    n = n / 2
    return n


def main():
    print(half(5))


if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<function name="half" type="Real" variable="result">
    <parameters>
        <parameter name="n" type="Integer" array="False"/>
    </parameters>
    <body>
        <declare name="result" type="Real" array="False" size=""/>
        <assign variable="n" expression="n / 2"/>
        <assign variable="result" expression="n"/>
    </body>
</function>
(n is an Integer parameter, `n / 2` = 2.5 is truncated to 2; half(5) returns 2.) Same with augmented assignment: `def add(total: int, x: float) -> float: total += x; return total` -> `<assign variable="total" expression="total + x"/>` into the Integer parameter; add(1, 0.5) returns 1 instead of 1.5.
```

### C8. Real value stored into an Integer array element is silently truncated

- **status:** fixed: a Real stored into an inferred Integer array widens the array to Real; an annotated `list[int]` is a clean error (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: types
- location: `py2fprg/convert.py: assign_to(), ast.Subscript branch — `compatible(elem_type, t)` treats Integer and Real as interchangeable in both directions.`
- expected: Python prints `0.5 1.5`. Since the element type is fixed at the in-place Declare, this should be a clean error like the existing String case ("cannot store a Real in an array of Integer; create it with `[0.0] * n`"), not a silent truncation.

```python
def main():
    n = 4
    xs = [0] * n
    for i in range(n):
        xs[i] = i / 2
    print(xs[1], xs[3])


if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<declare name="xs" type="Integer" array="True" size="n"/>
<for variable="i" start="0" end="n - 1" direction="inc" step="1">
    <assign variable="xs[i]" expression="i / 2"/>
</for>
<output expression="xs[1] & " " & xs[3]" newline="True"/>
(Flowgorithm prints `0 1`.)
```

### C9. Boolean operands in arithmetic are emitted verbatim (Flowgorithm has no bool->int coercion)

- **status:** converted: see C5
- severity: medium, votes: TTT, finder: types
- location: `py2fprg/convert.py: e_BinOp() (and infer() for ast.BinOp) — no check for a BOOLEAN operand under +, -, *, /, %, ^.`
- expected: Python prints `1 1`. Either a clean ConvertError at the `+` (hint: `if answer == correct: score += 1`) or an emitted If shape; infer() should not leave such variables silently typed Integer.

```python
def main():
    score = 0
    answer = 3
    correct = 3
    score = score + (answer == correct)
    flag = answer > 1
    count = 0
    count += flag
    print(score, count)


if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<assign variable="score" expression="score + (answer == correct)"/>
<assign variable="flag" expression="answer > 1"/>
<assign variable="count" expression="count + flag"/>
(converter exits 0 with no warning; --lint: WARNING: operand of '+' is Boolean; expected a number — twice. These expressions are type errors in Flowgorithm.)
```

### C10. `x: int = <Real>` (and `list[int] = [0.5] * n`) is accepted and silently truncates, unlike the str/bool mismatch which errors

- **status:** fixed: an `int` annotation (variable, `list[int]`, `-> int`, a later assignment) never takes a float: clean error with a hint (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: types
- location: `py2fprg/convert.py: assign_to() annotation branch and declare_array() — compatible(ann, t) accepts Real for an Integer annotation.`
- expected: Python prints `2.5 0.5 1.5`. A clean error like the existing "'x' is annotated String but assigned Integer" (only the Real->Integer direction slips through compatible()).

```python
def main():
    x: int = 2.5
    n = 3
    xs: list[int] = [0.5] * n
    y: int = n / 2
    print(x, xs[0], y)


if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
<declare name="x, n, idx, y" type="Integer" array="False" size=""/>
<assign variable="x" expression="2.5"/>
<assign variable="n" expression="3"/>
<declare name="xs" type="Integer" array="True" size="n"/>
<for variable="idx" start="0" end="n - 1" direction="inc" step="1">
    <assign variable="xs[idx]" expression="0.5"/>
</for>
<assign variable="y" expression="n / 2"/>
(Flowgorithm prints `2 0 1`.)
```

### C11. "cannot infer the type of variable" error points at the def line (1:1) or has no line at all for module-level programs

- **status:** fixed: VarInfo remembers its first assignment for the location (the repro itself is now the C5 Boolean error)
- severity: low, votes: TFT, finder: types
- location: `py2fprg/convert.py: hoisted_declarations() raises with self.f.node; VarInfo (created in var_assign()) does not remember its first-assignment node.`
- expected: `...py:3:5: error: cannot infer the type of variable 'k'` pointing at the first assignment `k = flag + 1` (Python itself prints 2 here; the un-inferable type comes from the Boolean + Integer case).

```python
def main():
    flag = 3 > 2
    k = flag + 1
    print(k)


if __name__ == "__main__":
    main()
```

Actual (at the time of the hunt):

```
p41_unknown_type_location.py:1:1: error: cannot infer the type of variable 'k'
    hint: annotate its first assignment, e.g. `k: int = ...`
(line 1 is `def main():`). For the module-level program `flag = 3 > 2\nk = flag + 1\nprint(k)` the message has no line: `p19_module_level_unknown_type.py: error: cannot infer the type of variable 'k'`.
```

### C12. Nested loops that reuse the loop variable (for _ in ...: for _ in ...) share one Flowgorithm counter

- **status:** converted: a loop whose variable is assigned inside it (also by a nested loop) counts with a hidden `<name>Counter` (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: loops
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py, FunctionConverter.s_For (var_assign(tgt.id, INTEGER, s) reuses the same VarInfo; no record of loop variables of enclosing loops)`
- expected: Each `for` needs its own counter: give `_` (and any target that is the loop variable of an enclosing, still-active for loop, or that an inner for-each assigns as its element variable) a fresh variable per loop (v, v2, ... exactly as fresh_var already does for for-each index variables), or raise a clean error such as "loop variable 'i' is already the loop variable of an enclosing for loop". Python rebinds the target from the iterator every iteration, so writes to it by inner loops never affect the outer iteration; Flowgorithm's For uses the variable itself as the counter.

```python
def main():
    for _ in range(3):
        for _ in range(2):
            print("x")

# same problem (all converted without any warning):
#   for i in range(3):
#       for i in range(2): print(i)
#   for k, x in enumerate(xs):
#       for k, y in enumerate(ys): print(k, x, y)
#   for x in range(3):
#       for x in xs: print(x)        # inner `x = xs[xIndex]` overwrites the outer counter
#   for i in range(2):
#       for j in range(2):
#           for i in range(2): s += 1
```

Actual (at the time of the hunt):

```
<declare name="v" type="Integer" array="False" size=""/>
<for variable="v" start="0" end="2" direction="inc" step="1">
    <for variable="v" start="0" end="1" direction="inc" step="1">
        <output expression=""x"" newline="True"/>
    </for>
</for>
(no converter warning; --lint reports 0 errors)

Python prints "x" 6 times. In Flowgorithm the inner For leaves v at its final value and the outer For then advances the same variable, so the outer loop either exits after a single pass (2 lines) or never terminates - never 6 lines. `for x in range(3): for x in xs:` emits <for variable="x" ...><for variable="xIndex" ...><assign variable="x" expression="xs[xIndex]"/> which clobbers the outer counter the same way.
```

### C13. Assignment to the for-loop variable inside the body changes the iteration count in Flowgorithm but not in Python

- **status:** converted: the loop counts with a hidden `<name>Counter` and assigns the Python variable at the top of each pass, so changing it does not change the iteration (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTT, finder: loops
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py, FunctionConverter.s_For / loop_body (the body is never scanned for Store targets equal to the loop variable)`
- expected: Reject it with a clean error ("assignment to the loop variable 'j' inside its for loop is not supported in Flowgorithm"), or iterate over a hidden fresh counter and assign the user's variable at the top of the body (the way for-each loops already do with xIndex / x).

```python
def main():
    total = 0
    for j in range(5):
        j += 1
        total += j
    print(total)

# also:
#   for i in range(5):
#       if i == 2:
#           i = 10
#       print(i)          # Python: 0 1 10 3 4  / Flowgorithm: 0 1 10
```

Actual (at the time of the hunt):

```
<for variable="j" start="0" end="4" direction="inc" step="1">
    <assign variable="j" expression="j + 1"/>
    <assign variable="total" expression="total + j"/>
</for>
<output expression="total" newline="True"/>
(no converter warning; --lint 0 errors)

Python prints 15 (j is rebound to 0,1,2,3,4 each iteration -> 1+2+3+4+5). Flowgorithm advances the counter from the modified value: j 0->1 (total 1), 2->3 (total 4), 4->5 (total 9), 6 > 4 stops -> prints 9.
```

### C14. Negative non-literal range step (-k, or a module constant STEP = -1) emits an increasing loop with a negative step and a wrong 'assumed positive' warning

- **status:** fixed: `-k` and module constants (test: `BugHuntRegressionTest`)
- severity: low, votes: TTF, finder: loops
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py, FunctionConverter.range_bounds and int_literal (only ast.Constant / -Constant are recognised)`
- expected: `-k` is syntactically negative: emit direction="dec" step="k" end="1". A module constant is a known literal (resolve_constant already returns its value): STEP = -1 -> direction="dec" step="1" end="1", and no warning for POS = 2. For a step whose sign really is unknown, a clean error is better than a loop that silently never runs; the warning text 'assumed positive' is wrong for the first two cases.

```python
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
```

Actual (at the time of the hunt):

```
prog.py:7: warning: non-literal range step assumed positive
prog.py:9: warning: non-literal range step assumed positive
prog.py:11: warning: non-literal range step assumed positive
<for variable="i" start="n" end="-1" direction="inc" step="-k">
<for variable="i" start="n" end="-1" direction="inc" step="STEP">
<for variable="i" start="0" end="n - 1" direction="inc" step="POS">

Python counts n, n-1, ..., 1 for the first two loops; the emitted loops start at n with an inclusive end of -1 and direction inc, so they run zero times (and Flowgorithm's step is documented as a positive expression, so step="-k" is not even well-formed).
```

### C15. negate() skips e_Compare's operand type check, so a break condition comparing a String with an Integer is accepted while the same `if` is rejected

- **status:** fixed: negate() runs the same operand type check as e_Compare (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: loops
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py, FunctionConverter.negate (builds the flipped comparison from sub() directly instead of going through e_Compare's compatibility check)`
- expected: The same "comparing String with Integer" error for the break condition (Flowgorithm cannot compare a String with an Integer, so the emitted Do loop is not runnable).

```python
def main():
    s = ""
    while True:
        s = input("word")
        if s == 5:
            break
    print(s)

# for comparison, this is rejected:
#   if s == 5:
#       print("five")      -> prog.py:3:8: error: comparing String with Integer
```

Actual (at the time of the hunt):

```
<do expression="s != 5">
    <output expression=""word"" newline="True"/>
    <input variable="s"/>
</do>
(converter silent; lint: WARNING '!=' compares String with Integer). The identical comparison in an `if` statement gives "error: comparing String with Integer".
```

### C16. For-loop counter read after the loop (including in a Do condition) assumes Python's last value; Flowgorithm's counter likely ends one step past the end

- **status:** converted: a loop whose variable is read after it (found by a may-analysis; the function is converted again) counts with a hidden counter, so the variable keeps Python's last value (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: loops
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py, FunctionConverter.s_For (no tracking of reads of the loop variable after its loop)`
- expected: Either confirm the final counter value matches Python's (n-1) or warn/error when the loop variable of a for loop is read after the loop (or used in an enclosing Do condition), since the two languages differ on what the variable holds after the loop.

```python
def main():
    n = int(input("n"))
    while True:
        for i in range(n):
            print(i)
        if i == n - 1:
            break
    print(i)

# simpler:
#   for i in range(n):
#       print(i)
#   print("last", i)      # Python: n-1
```

Actual (at the time of the hunt):

```
<do expression="i != n - 1">
    <for variable="i" start="0" end="n - 1" direction="inc" step="1">
        <output expression="i" newline="True"/>
    </for>
</do>
<output expression="i" newline="True"/>
(no converter warning)

Python: after the for, i == n-1, so the Do exits after one pass and prints n-1. If Flowgorithm's For leaves the counter one step past the end (i == n, as C/BASIC-style counted loops do), the Do condition never becomes false (infinite loop) and `print("last", i)` shows n instead of n-1. Caveat: I could not reach the Flowgorithm documentation (site certificate expired, archive blocked) to confirm the counter's final value - verify in Flowgorithm before acting.
```

### C17. Early return nested inside an if is silently overridden by the code after the outer if

- **status:** fixed: statements after an if-chain that may return move into every branch that does not return (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py: FunctionConverter.normalize_returns (line 349, the `b_ret, e_ret = ends_with_return(...)` branch at line 355) together with ends_with_return (line 116)`
- expected: Either a clean error ("return on some paths of a nested if followed by more code is not supported") or the trailing statements duplicated into every path that does not return (append `rest` to s.body as well as to s.orelse and let the nested block's normalize_returns move it under the inner if). normalize_returns only moves `rest` when ends_with_return() is true for a whole branch; when contains_return() is true for a branch but ends_with_return() is false (return reachable on only some paths) it leaves `rest` after the If, so the later assignment to the return variable (or the later statements) runs after the early return.

```python
def is_valid(age: int, has_id: bool) -> bool:
    if age >= 18:
        if has_id:
            return True
    return False


def main():
    print(is_valid(20, True))
```

Actual (at the time of the hunt):

```
<function name="isValid" type="Boolean" variable="result">
  ...
  <declare name="result" type="Boolean" array="False" size=""/>
  <if expression="age >= 18">
      <then>
          <if expression="hasId">
              <then>
                  <assign variable="result" expression="true"/>
              </then>
              <else/>
          </if>
      </then>
      <else/>
  </if>
  <assign variable="result" expression="false"/>

(no warning, lint 0 errors). The flowchart always returns false: the inner `result = true` is followed by the unconditional `result = false`. Python prints True. Same silent mis-conversion for a nested return with a trailing statement in the outer then-body (classify(4): Python 'positive even', flowchart 'other'), for a void function (`if a>0: if b>0: print('both'); return` ... `print('tail')` prints 'tail' after 'both'), and for a return in an elif branch (see the next finding).
```

### C18. Return in an elif branch (other branches fall through) is overridden by the trailing code

- **status:** fixed: same mechanism as C17 (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py: FunctionConverter.normalize_returns (line 349) / ends_with_return (line 116)`
- expected: The `print('tail'); return 0` tail must only run on the paths that did not return: i.e. inside the then-branch of `n > 10` and inside the else of `n > 5` (or a clean error). ends_with_return(s.orelse) is false because the inner if has no else, so normalize_returns appends nothing and the tail is emitted after the whole if chain.

```python
def f(n: int) -> int:
    if n > 10:
        print("big")
    elif n > 5:
        return 5
    print("tail")
    return 0


def main():
    print(f(7))
```

Actual (at the time of the hunt):

```
<if expression="n > 10">
    <then>
        <output expression=""big"" newline="True"/>
    </then>
    <else>
        <if expression="n > 5">
            <then>
                <assign variable="result" expression="5"/>
            </then>
            <else/>
        </if>
    </else>
</if>
<output expression=""tail"" newline="True"/>
<assign variable="result" expression="0"/>

For n = 7 the flowchart prints 'tail' and returns 0; Python returns 5 and prints nothing. No warning, lint clean.
```

### C19. Parameter reassigned with a Real keeps its Integer parameter type: result truncated

- **status:** fixed: see C7
- severity: medium, votes: TTT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py: FunctionConverter.var_assign (line 942, `info.type = join_types(info.type, t)` with no is_param check)`
- expected: var_assign joins the parameter's VarInfo type to Real (so later inference believes x is Real) but the already emitted <parameter> stays Integer. For a parameter (info.is_param) a widening/different joined type should be an error ("parameter 'x' is int but is assigned a Real; use a local variable"), or the assignment should go to a fresh local used from then on.

```python
def half(x: int) -> float:
    x = x / 2
    return x


def main():
    print(half(5))
```

Actual (at the time of the hunt):

```
<function name="half" type="Real" variable="result">
    <parameters>
        <parameter name="x" type="Integer" array="False"/>
    </parameters>
    <body>
        <declare name="result" type="Real" array="False" size=""/>
        <assign variable="x" expression="x / 2"/>
        <assign variable="result" expression="x"/>
    </body>
</function>

x is an Integer parameter, so `x = x / 2` stores 2 and half(5) returns 2.0; Python prints 2.5. No warning.
```

### C20. infer_params only uses the first literal call site: later Real literals are truncated into an Integer parameter

- **status:** fixed: parameter types join the default and every literal argument in the program's functions; a conflict is a clean error (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/project.py: ProgramBuilder.infer_params (line 405; guard at line 413)`
- expected: x inferred as Real (join of Integer and Real), function type Real. In infer_params the join `p.type = join_types(p.type, literal_type(v))` is guarded by `if p.type is None:`, so after the first literal every other call site is ignored and the join_types call is dead code; the join must run for every literal argument of an inferred parameter (track which params are inferred rather than annotated) and a Real literal passed to an inferred Integer parameter must at least warn.

```python
def twice(x):
    return x * 2


def main():
    print(twice(1))
    print(twice(2.5))
```

Actual (at the time of the hunt):

```
<output expression="twice(1)" newline="True"/>
<output expression="twice(2.5)" newline="True"/>
...
<function name="twice" type="Integer" variable="result">
    <parameters>
        <parameter name="x" type="Integer" array="False"/>
    </parameters>

x is Integer, so twice(2.5) receives 2 and prints 4 (and the function type is Integer); Python prints 2 and 5.0. No warning, lint clean.
```

### C21. Parameter typed from an int default is not widened by Real call-site arguments: silent truncation

- **status:** fixed: see C20
- severity: medium, votes: TTT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/project.py: ProgramBuilder.register_function (line 264, `t = literal_type(dv)`) and infer_params (line 405)`
- expected: factor inferred as Real: the default literal's type should only seed the parameter type and be joined with the literal types at the call sites (infer_params skips the parameter entirely because register_function already set p.type from the default), or passing a Real literal to a default-typed Integer parameter should be reported.

```python
def scale(x: float, factor=2) -> float:
    return x * factor


def main():
    print(scale(3.0, 2.5))
    print(scale(3.0))
```

Actual (at the time of the hunt):

```
<output expression="scale(3.0, 2.5)" newline="True"/>
<output expression="scale(3.0, 2)" newline="True"/>
...
<function name="scale" type="Real" variable="result">
    <parameters>
        <parameter name="x" type="Real" array="False"/>
        <parameter name="factor" type="Integer" array="False"/>
    </parameters>

factor is Integer because of the default `2`, so scale(3.0, 2.5) computes 3.0 * 2 = 6.0; Python prints 7.5. No warning (user_call's compatible() accepts Real for Integer).
```

### C22. infer_params reads call sites inside `# fg: ignore` functions and reports an order-dependent, misleading type error

- **status:** fixed: only call sites in converted functions count (test: `BugHuntRegressionTest`)
- severity: low, votes: TTT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/project.py: ProgramBuilder.infer_params (line 405; walks every module tree without skipping fi.ignored functions; `except TypeError: p.type = None` at line 418)`
- expected: Calls inside ignored functions (and module-level/test code that is not converted) should not participate in inference; a genuine conflict between converted call sites should produce the "parameter 'x' of show() needs a type annotation" error instead of blaming one call site.

```python
# fg: ignore
def debug_show():
    show("debug")


def show(x):
    print(x)


def main():
    show(1)
```

Actual (at the time of the hunt):

```
prog.py:11:10: error: parameter 'x' expects String, got Integer

The ignored helper's literal "debug" (walked first) types x as String, and the real call show(1) is then rejected. Similarly `show(1); show("a"); show(2)` fails at show("a") with "expects Integer, got String" because the conflict resets p.type to None and the next literal re-seeds it, so the outcome depends on call order.
```

### C23. `return None` is rejected with misleading errors ("unexpected return value" / "None has no Flowgorithm equivalent")

- **status:** fixed: `return None` is a bare return, also without `-> None` (test: `BugHuntRegressionTest`)
- severity: low, votes: TTF, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py: FunctionConverter.do_return (line 426, `if s.value is None` at 429 / `unexpected return value` at 436); /Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/project.py: register_function (has_value_return)`
- expected: `return None` is the same as a bare `return` in a void function and should convert like it (the if with the rest moved into the else), or at least produce a message that says so. do_return only recognises `s.value is None`; a Constant(None) value should be treated identically, and has_value_return should ignore it.

```python
def greet(name: str) -> None:
    if name == "":
        return None
    print("Hello " + name)


def main():
    greet("Bob")
```

Actual (at the time of the hunt):

```
prog.py:3:9: error: unexpected return value

Without the `-> None` annotation the same program gives `prog.py:3:16: error: None has no Flowgorithm equivalent` (register_function's has_value_return also counts `return None` as a value return, so the function is treated as value-returning).
```

### C24. Comment inside an else branch that returns is emitted in the then branch

- **status:** fixed: statements moved by the early-return normalisation keep their comments and no longer re-scan the else branch (test: `BugHuntRegressionTest`)
- severity: low, votes: TFT, finder: functions
- location: `/Users/alekseitatuzov/personal/code/flowgorithm/py2fprg/convert.py: FunctionConverter.normalize_returns (line 349, `s.body = list(s.body) + list(rest)`) with s_If/find_else_line (lines 500 / 296) and block()'s take_comments ranges`
- expected: The comment belongs to the else branch, before `result = -1`. When normalize_returns appends the trailing statements to s.body (else returns), the then-block's take_comments range for the first moved statement (prev_end+1 .. its lineno) spans the else branch's source lines and consumes its comments; moved statements should only collect comments from their own original range (or the else block should be converted first).

```python
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
```

Actual (at the time of the hunt):

```
<if expression="n > 0">
    <then>
        <output expression=""pos"" newline="True"/>
        <comment text="negative case"/>
        <output expression=""after"" newline="True"/>
        <assign variable="result" expression="1"/>
    </then>
    <else>
        <assign variable="result" expression="-1"/>
    </else>
</if>
```

### C25. Module-level program: `# fg: ignore` on a top-level statement/def/class also deletes the NEXT converted statement

- **status:** fixed: one `# fg: ignore` pre-pass (`py2fprg/layout.py`) for module-level and in-function code (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: comments
- location: `py2fprg/project.py ProgramBuilder.build (module-level branch marks only the lines of defs as consumed: `conv.consumed.update(range(other.node.lineno, ...))`; the lines of ignored top-level statements/classes and the `# fg: ignore` line(s) above an ignored def/class/statement found by is_ignored() are never consumed) together with py2fprg/convert.py FunctionConverter.block/take_comments, whose range `prev_end + 1 .. attach_end` for the next statement then spans the stale `fg: ignore` and sets ignore=True for the wrong statement.`
- expected: a.py: <assign variable="x" expression="5"/> followed by <output expression="x * 2" newline="True"/>. b.py: Main with x declared, assigned 5 and output. c.py: both outputs. Only the statement carrying the directive may disappear.

```python
# a.py, alone in its directory; cd flowgorithm && python3 -m py2fprg a.py --stdout --no-metadata --lint
"""Module-level program with an ignored debugging statement."""
x = 5
# fg: ignore
print("debug: x is", x)
print(x * 2)

# ---- variant b.py: directive above an ignored def ----
"""Module-level program with an ignored helper def above the code."""
# fg: ignore
def debug_helper():
    pass

x = 5
print(x)

# ---- variant c.py: ignored class ----
"""Module-level program with an ignored class."""
# fg: ignore
class Helper:
    def method(self):
        return 1

print("hi")
print("there")
```

Actual (at the time of the hunt):

```
a.py converts without any warning to a Main whose whole body is
    <declare name="x" type="Integer" array="False" size=""/>
    <assign variable="x" expression="5"/>
(print(x * 2) has vanished together with the ignored print).
b.py: `b.py:7:7: error: 'x' is not defined before use` (x = 5 was dropped).
c.py: Main body is only `<output expression=""there"" newline="True"/>` (print("hi") dropped).
```

### C26. `# fg: ignore` on `def main()` crashes with an AttributeError traceback

- **status:** fixed: clean error (test: `BugHuntRegressionTest`)
- severity: high, votes: TTT, finder: comments
- location: `py2fprg/project.py ProgramBuilder.build -> visit(): `caller.py_name` is evaluated with caller=None for the entry function; check fi.ignored for main_fi before the call-graph walk.`
- expected: A clean `file:2: error: main() cannot be marked `fg: ignore`` (or: the directive is disregarded for main with a warning).

```python
# fg: ignore
def main():
    print("hi")
```

Actual (at the time of the hunt):

```
Traceback (most recent call last):
  ...
  File ".../py2fprg/__init__.py", line 62, in convert_path
    program = b.build(m, title=title)
  File ".../py2fprg/project.py", line 469, in build
    visit(main_fi, None)
  File ".../py2fprg/project.py", line 460, in visit
    f"{caller.py_name}()", fi.node, filename=fi.module.path)
AttributeError: 'NoneType' object has no attribute 'py_name'
```

### C27. `# fg: ignore` on an `elif` also deletes the following `else` branch

- **status:** fixed: ignoring an elif keeps the rest of the chain (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTT, finder: comments
- location: `py2fprg/convert.py FunctionConverter.block: the elif is an ast.If whose orelse carries the rest of the chain; the ignore branch drops the whole node. Handle in s_If/block by splicing s.orelse in when an elif is ignored.`
- expected: <else>
    <output expression=""neg"" newline="True"/>
</else>
(only the elif's own branch is left out: replace the nested If by its orelse), or an error saying an elif cannot be ignored.

```python
def main():
    x = int(input("x?"))
    if x > 0:
        print("pos")
    elif x == 0:  # fg: ignore
        print("zero (debug)")
    else:
        print("neg")
```

Actual (at the time of the hunt):

```
<if expression="x > 0">
    <then>
        <output expression=""pos"" newline="True"/>
    </then>
    <else/>
</if>
(print("neg") is gone without a warning; Python prints "neg" for x < 0).
```

### C28. `# fg: ignore` on a continuation line of a multi-line compound header removes the first body statement instead of the compound statement

- **status:** fixed: a header ends at its real ':' (tokenizer), so a directive on any header line removes the whole statement (test: `BugHuntRegressionTest`)
- severity: medium, votes: TFT, finder: comments
- location: `py2fprg/convert.py FunctionConverter.block: `attach_end = s.lineno if is_compound(s) else ...` only covers the first header line; directives on later header lines fall into the body block's take_comments range (block(s.body, s.lineno + 1, ...) in s_If/s_While/s_For). Use the last header line (s.body[0].lineno - 1, or the colon line) as attach_end/body start.`
- expected: The whole `if` left out: <assign a 1/> <assign b 2/> <output "done"/>.

```python
def main():
    a = 1
    b = 2
    if (a > 0
            and b > 0):  # fg: ignore
        print("debug both positive")
    print("done")
```

Actual (at the time of the hunt):

```
<assign variable="a" expression="1"/>
<assign variable="b" expression="2"/>
<if expression="a > 0 and b > 0">
    <then/>
    <else/>
</if>
<output expression=""done"" newline="True"/>
(the wrong statement was removed: the if survives empty, its body is gone).
```

### C29. Decorated def: `# fg: ignore` as a trailing comment on the `def` line is not recognised (README: on a def or the line above it)

- **status:** fixed: a directive anywhere from the decorators to the def's ':' applies to the def (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTT, finder: comments
- location: `py2fprg/project.py ProgramBuilder.is_ignored: `first = min(s.lineno, decorator linenos)`; candidates = [first] + contiguous comment lines above it, so s.lineno (the def line) is not examined when decorators exist. Add s.lineno (and the lines between decorators and def) to candidates.`
- expected: cached is ignored and the program converts (Main: <output expression="1" newline="True"/>).

```python
import functools


@functools.lru_cache(maxsize=None)
def cached(n: int) -> int:  # fg: ignore
    return n * 2


def main():
    print(1)
```

Actual (at the time of the hunt):

```
p07.py:5:1: error: decorators are not supported
    hint: mark the function with `# fg: ignore` if it is only used by tests
(the hint suggests exactly what the file already does). Placing the directive above the decorator or trailing on the decorator line works.
```

### C30. While-first `while True` pattern: every comment and directive between `while True:` and the end of `if cond: break` is silently dropped, including `# fg: breakpoint` and `# fg: comment`

- **status:** fixed: comments and directives inside the break-if are kept (test: `BugHuntRegressionTest`)
- severity: medium, votes: TFT, finder: comments
- location: `py2fprg/convert.py FunctionConverter.s_While (While-first branch): `self.take_comments(body[0].lineno, body[0].end_lineno)` discards the returned items, and `loop_body(body[1:], body[0].end_lineno + 1, ...)` starts after the break-if, so lines s.lineno+1 .. body[0].lineno-1 are never scanned by anyone. Emit the items (and scan from s.lineno + 1) instead of discarding them.`
- expected: <breakpoint/> and <comment text="explicit on exit line"/> emitted (before the While shape or as the first shapes of its body); plain comments likewise kept, as they are in the Do-loop variant and in ordinary while loops.

```python
def main():
    x = 10
    while True:
        # fg: breakpoint
        if x <= 0:  # fg: comment explicit on exit line
            break
        x -= 3
    print(x)

# ---- plain-comment variant ----
def main():
    x = 10
    while True:
        # loop until x is small enough
        if x <= 0:  # exit condition
            break
        x -= 3
    print(x)
```

Actual (at the time of the hunt):

```
<assign variable="x" expression="10"/>
<while expression="x > 0">
    <assign variable="x" expression="x - 3"/>
</while>
<output expression="x" newline="True"/>
(no <breakpoint/>, no <comment/> at all; in the variant both plain comments are lost). No warning.
```

### C31. Structural pre-checks run before `fg: ignore` is applied: an ignored debug print as the last statement of a `while True` loop (and ignored return/nested def) still rejects the function

- **status:** fixed: ignored statements are removed before any structural check runs (test: `BugHuntRegressionTest`)
- severity: medium, votes: TTT, finder: comments
- location: `py2fprg/convert.py FunctionConverter.s_While (is_break_if(body[-1]) / has_break_or_continue inspect the raw body), block() (contains_return before the ignore check), walk_function(); py2fprg/project.py ProgramBuilder.register_function (has_value_return walks ignored statements). Strip ignored statements once, up front, before these checks.`
- expected: p25: <do expression="x <= 3"><assign variable="x" expression="x + 1"/></do> <output expression="x" newline="True"/> (the ignored print is simply left out, as README promises for `# fg: ignore` on a statement). Variants: ignored statements do not participate in the checks.

```python
def main():
    x = 0
    while True:
        x += 1
        if x > 3:
            break
        print("debug", x)  # fg: ignore
    print(x)

# ---- variants ----
def main():
    for i in range(3):
        if i == 2:
            return  # fg: ignore
        print(i)

def g():
    # fg: ignore
    def inner():
        return 1
    print(2)

def main():
    g()
```

Actual (at the time of the hunt):

```
p25.py:3:5: error: `while True` needs a single `if cond: break` as the first statement (-> While loop) or the last statement (-> Do loop) of its body
variants: `p21.py:4:13: error: return inside a loop is not supported`; `p31.py:3:5: error: nested function definitions are not supported` (even though g() is void; register_function's return scan sees `return 1` inside the ignored def and make_return_var/walk_function raises).
```

### C32. Comments on `else:` lines and on the first line of a `def` are silently lost

- **status:** fixed: else-line and def-line comments are kept (test: `BugHuntRegressionTest`)
- severity: low, votes: TFT, finder: comments
- location: `py2fprg/convert.py FunctionConverter.s_If: then_end = else_line - 1 and else_start = else_line + 1 leave the else line unscanned; FunctionConverter.convert: block(f.body, f.node.lineno + 1, ...) skips the def's first line (take_comments is never called for it).`
- expected: <comment text="negative or zero"/> as the first shape of the else branch; def-line comments at the start of the function body (before/after the docstring comment).

```python
def main():
    x = int(input("x?"))
    if x > 0:
        print("pos")
    else:  # negative or zero
        print("non-pos")
    # trailing

# ---- def-line variant ----
def add(a: int,  # the first
        b: int) -> int:  # the second
    return a + b


def main():
    print(add(1, 2))
```

Actual (at the time of the hunt):

```
first program: no <comment text="negative or zero"/> anywhere (the else branch is just <output "non-pos"/>; "trailing" is kept). Variant: add's body is
    <declare name="result" .../>
    <comment text="the second"/>
    <assign variable="result" expression="a + b"/>
("the first", on the def line, is gone; `def f():  # note` loses its comment the same way).
```

## Rejected by verification (19)

Mostly findings that no longer reproduced after the review's fixes, plus documented limitations.

- `**` with a negative exponent is inferred Integer, so 2 ** -1 becomes 0 instead of 0.5
  - reproduce: Running the repro exactly as given produces `<declare name="x" type="Real" .../>` with `2 ^ -1`, not the reported Integer declaration, and fprg_run.py prints 0.5 like Python (convert.py infer() already returns REAL for Pow with a negative literal exponent at line 1480); only the secondary
- `if not n:` / `if n:` / `a and b` on non-Boolean values are emitted verbatim without a diagnostic
  - reproduce: Running the exact repro program produced `<if expression="n == 0">` and `<if expression="n != 0">` with 0 lint errors (not the verbatim `not n` / `n` the report claims), and the secondary cases are also handled (`if a and b:` -> `a != 0 and b != 0`, `while s:` -> `s != ""`, `if not xs:` -
- Single-expression f-string `s = f"{n}"` assigns a bare Integer/Boolean to a String variable
  - reproduce: Running the repro exactly as given produces `<assign variable="s" expression="ToString(n)"/>` (not the reported bare `n`) with fprg_lint reporting 0 errors, and the variants `f"{a < b}"` / `f"{a + b}"` likewise emit `ToString(a < b)` / `ToString(a + b)` while a String-typed `f"{name}"` co
- Parenthesized comparison as the LEFT operand of another comparison loses its parentheses (lint warns about a chained comparison)
  - reproduce: Running the converter on the repro produced exactly `<assign variable="same" expression="a < b == (b < a)"/>` with the quoted fprg_lint chained-comparison warning, and the variants `(a < b) == c`, `(a == b) == (d == e)`, `(a < b) != (b < a)` and the negated `if (a < b) == c: break` likewi
- Function whose only return is a module constant (or imported constant / math.pi) returns 0 / "" / 0.0 — the constant is shadowed by the return variable
  - reproduce: Running the exact repro program through `python3 -m py2fprg ... --stdout --no-metadata --lint` produces the expected output, not the reported one: getLimit is emitted with variable="result", `<declare name="result, LIMIT" type="Integer"/>`, `<assign variable="LIMIT" expression="10"/>` and
- Non-Boolean conditions (Python truthiness: `if n:`, `while n:`, `if not s:`) are emitted verbatim
  - reproduce: Running the verbatim repro through `python3 -m py2fprg --stdout --no-metadata --lint` emits `<if expression="n != 0">`, `<while expression="n != 0">` and `<if expression="s == """>` (the report's expected output, not the reported verbatim `n`/`n`/`not s`), lint shows 0 errors with only th
- `int ** negative int` is inferred Integer (Python gives float) -> result truncated to 0
  - reproduce: Running the exact repro program produced `<declare name="x" type="Real"/>` and `<declare name="y" type="Integer"/>` (not the reported combined Integer declare), and convert.py:1480 explicitly returns REAL for `ast.Pow` with a negative literal exponent, so the reported Integer truncation o
- `return xs` of a local array gives the misleading error "'xs' is already defined; arrays cannot be re-created"
  - reproduce: Running the repro exactly as given produced the reported output verbatim ("p18_ret_var_array_name.py:2:5: error: 'xs' is already defined; arrays cannot be re-created" on the first and only definition of xs), and the cause matches the location guess: convert.py:186 calls make_return_var() 
- while with a non-boolean (truthiness) condition is emitted verbatim: `while n:` -> <while expression="n">
  - reproduce: Not reproducible: running the exact repro through `python3 -m py2fprg repro.py --stdout --no-metadata --lint` emits `<while expression="n != 0">`, `<while expression="n == 0">`, `<while expression="s != """>` and `<while expression="remaining(n) != 0">` (the report's EXPECTED output) with
- `while 1:` is not recognised as `while True:` - the break pattern is rejected with a misleading error, and without break an Integer condition is emitted
  - reproduce: Only half the report reproduces: the break variant does give the verbatim error "break/continue inside a while loop is not supported" (convert.py:553 tests `value is True`, false for int 1), but that is the README-documented behaviour (break only inside the two `while True` patterns, othe
- The canonical array-fill loop `xs[i] = int(input(...))` is rejected
  - reproduce: Running the repro program exactly as given reproduced the reported error verbatim (`prog.py:5:21: error: input() must be assigned directly to a variable` plus the hint, exit 1, not fixed), while `xs[i] = i * 2` and `n = int(input(...))` each convert on their own, the report's expected `<i
- `return NAME` of a module constant, imported constant, function or undefined name makes NAME an unassigned return variable (function returns 0)
  - reproduce: Running the repro program as given now yields the REPORTED EXPECTED output (variable="result", `maxTries = 10` copied in, `result = maxTries`, lint 0 errors) because make_return_var in py2fprg/convert.py (now line 223) already excludes names that resolve to module constants, callees and i
- Malformed string annotation reports `<unknown>:1: error: invalid syntax` instead of the file and line
  - reproduce: Running the given repro program prints "prog.py:1: error: syntax error: invalid syntax" (the SyntaxError from ast.parse of the string annotation is caught in ProgramBuilder.discover at py2fprg/project.py:173 and re-raised as a ConvertError carrying the real file path), not the reported "<
- Passing a list literal to a list parameter says "parameter 'xs' expects a list"
  - reproduce: Running the repro exactly as given prints "prog.py:11:17: error: parameter 'xs' expects a list" on the [4, 5] literal argument, matching the report byte-for-byte, and the code confirms the mechanism: infer() in py2fprg/convert.py has no ast.List branch so returns None, and user_call (now 
- Returning a list variable is reported as "'xs' is already defined; arrays cannot be re-created" at the array creation line
  - reproduce: Running the repro produced exactly "prog.py:2:5: error: 'xs' is already defined; arrays cannot be re-created" (exit 1), and the code confirms the diagnosis: make_return_var (convert.py:223) pre-registers the returned name 'xs' as a scalar in self.vars before the body is converted, so decl
- `# fg: ignore` on an `if ...: return` block silently deletes all the code that follows it in the function
  - reproduce: Running the exact repro through the repo's py2fprg (confirmed imported from /Users/alekseitatuzov/personal/code/flowgorithm/py2fprg) produced the report's EXPECTED output, not its ACTUAL: f's body is `<declare name="result" .../>` followed by `<assign variable="result" expression="n * 2"/
- An ignored call still pulls its callee into the call graph, so a debugging helper cannot be called from converted code even when the call is ignored
  - reproduce: Not reproducible: both repro programs (p05.py with the ignored helper plus same-line `# fg: ignore` call, and p26.py with only the call ignored via the comment above it) convert with exit 0 and lint-clean, producing exactly the expected Main (`<assign variable="x" expression="1"/>` + `<ou
- Module-level `fg: ignore` placement rules differ from in-function rules: a blank line after the directive, or the directive trailing the last line of a multi-line statement, is not honoured
  - reproduce: Reproduced exactly: both module-level variants (blank line after `# fg: ignore`, and the directive trailing the last line of a multi-line statement) fail with "module-level code is not supported when main() exists / hint: ... mark it `# fg: ignore`" (exit 1), while the same placements ins
- Module-level program: a function's trailing comments are duplicated into Main
  - reproduce: Running the exact repro program through the converter produced Main with only the output node and the "helper's trailing note" comment appearing once, at the end of helper; the bug no longer reproduces because py2fprg/project.py line 534 now consumes ProgramBuilder.def_lines(...), which a

## Unverified leads (64), triaged in the second session

Each lead was reproduced before it was fixed; *fixed* items have tests in `BugHuntRegressionTest` or
`ProjectLayoutTest`. Several are duplicates of confirmed findings above.

- Comment between an `if ...: return` block and the code after it is placed inside the then-branch — **fixed (review; still covered)**
- Comments and directives trailing inside an ignored compound statement leak out of it — **fixed: the indented trailing comments go with the ignored statement**
- Misspelled directives outside function bodies never warn, and an `fg: ignore` consumed by a block's trailing-comment scan is silently discarded — **fixed: unknown directives warn at load time; an orphaned `fg: ignore` warns**
- if __name__ == "__main__": body is silently dropped when the module has no main() — **fixed: the guard decides the entry (it may call any function)**
- `# fg: ignore` above an ignored def/statement in a module-level program drops the NEXT top-level statement — **fixed (C25)**
- UnicodeDecodeError traceback when any .py file in the project is not UTF-8 (valid PEP 263 coding cookie) — **fixed: PEP 263 cookies are honoured; an unreadable file is skipped with a warning**
- AttributeError crash when main() itself carries `# fg: ignore` — **fixed (C26)**
- __init__.py as the entry: its relative imports resolve one package level too high; a root __init__.py is never discovered — **fixed for relative imports (a package's own name is its package); a root __init__.py is still not a module**
- `from . import mod` fails in single-file mode or when pointed at the package directory, while `from .mod import f` works — **fixed**
- Run from a parent directory, a root-level module shadows the sibling module of the same name (wrong function converted) — **fixed: a sibling module wins**
- `import a.b` + `a.b.f()` is rejected when run from a parent directory and a/ has no __init__.py — **fixed: folders without __init__.py count as packages**
- Names re-exported by a package __init__.py are not followed (misleading 'no Flowgorithm equivalent' error) — **fixed: imports are followed**
- Module-level variable modified at top level is copied into functions with its initial literal value — **fixed: such a name is a variable; reading it in a function is a clean error**
- A constant defined before a `from m import X` of the same name wins over the import (Python: last binding wins) — **fixed: the last binding wins**
- A project with one module-level program and one defs-only helper module is rejected as 'no program found' — **fixed**
- import statements inside a function body are ignored, producing an unrelated 'unsupported call' error — **fixed: they are registered (module-wide)**
- Spurious 'unreachable code' warning when two entry modules share a helper (AST mutated by the first build) — **fixed (review; still covered)**
- Local variable shadowing an imported constant is rejected unless it happens to be the return variable — **fixed: a name assigned in a function is local there (Python's rule)**
- Single-expression f-string drops the string conversion: s = f"{n}" emits Assign s = n (Integer into String); also Len(n), n == "7", shout(n) — **fixed (review)**
- Control characters in comments/docstrings/directives are written as  etc., producing ill-formed XML that no parser (nor Flowgorithm) will open — **fixed: dropped from attribute text; strings use ToChar()**
- input() into an array element is rejected although Flowgorithm's Input accepts arr[i] and both halves are advertised as supported — **fixed (batch 1; covered by a differential test)**
- print() of a whole list is silently emitted as Output xs (an array), which Flowgorithm cannot print, instead of a conversion error — **fixed (review)**
- Empty format spec f"{n:}" (valid Python, same as f"{n}") is rejected with a misleading 'nested format specs' error — **not reproducible on Python 3.12+**
- Upper-case fixed-point spec f"{x:.2F}" (valid Python, identical to .2f for finite values) is rejected — **fixed**
- input() prompts are emitted with newline=True, so input("") prints a blank line Python never prints and input("Name:\n") prints two line breaks instead of one — **fixed for `input("")` / `input()` (no Output); prompts keep their own line by design**
- Module-level programs turn the shebang and coding comments into Comment shapes ('!/usr/bin/env python3', '-*- coding: utf-8 -*-') — **fixed: shebang, coding line and tool pragmas (`# noqa`, `# type: ...`) never become comments**
- return CONSTANT (module constant, directly or via from-import alias) emits no assignment: the function returns 0 — **fixed (review)**
- return pi / return e (from math import ...) returns 0.0: imported library constant adopted as an unassigned return variable — **fixed (review)**
- Un-annotated `def f(): return CONSTANT` is rejected with 'cannot infer the return type' although the constant's type is known — **not reproducible**
- Module-level name that is a literal first and later re-assigned non-literally stays a 'constant': functions get the stale literal (module-level program) — **fixed (see 'Module-level variable modified')**
- Module-level `n = int(input(...))` after a literal `n = 5` is silently dropped in a def-main module — **not silent: a clean 'module-level code' error**
- Module-level code in a non-entry module is silently ignored (and leaves stale constant values) — **fixed: a warning**
- `# fg: ignore` on a call statement does not stop the 'marked fg: ignore but is called from' error — **fixed (review)**
- A local (or for-loop) variable named like a module-level literal is rejected as 'cannot assign to constant', but accepted when the same local is returned — **fixed (local scope rule)**
- Rename warning always blames case-insensitivity, and non-ASCII letters are dropped from identifiers without any warning — **fixed: non-ASCII letters are transliterated (`größe` -> `grosse`, Cyrillic too); the warning names all three rules**
- Returning a list variable from an un-annotated function reports "'xs' is already defined; arrays cannot be re-created" — **fixed: 'functions cannot return arrays'**
- `# fg: ignore` on `def main()` crashes with AttributeError instead of a clean error — **fixed (C26)**
- Non-UTF-8 source file (valid Python with a PEP 263 coding cookie) crashes with UnicodeDecodeError, even if it is an unrelated sibling file — **fixed**
- RecursionError on a long left-nested `+` chain (about 340 operands or more; ~600 for string concatenation in print()) — **fixed: the recursion limit is raised while converting (and linting); 3000 terms work**
- Augmented assignment to an array element evaluates the index expression twice, so `tally[random.randint(1, 6)] += 1` draws two different random numbers (and `counts[roll()] += 1` prompts for input twice) — **converted: the index is evaluated once, into a variable**
- Negative index given as an expression (`xs[-i]`, `xs[-(i + 1)]`) is emitted verbatim; only literal negatives are translated to `Size(xs) - k` — **fixed: `xs[-i]` counts from the end only when -i is negative, as in Python**
- `# fg: ignore` functions are still validated for parameters, defaults and annotations, contradicting README ('it may use any Python') — **fixed**
- Project with two runnable modules: calling the other module's main() is rejected as 'main() cannot be called' because FuncInfo.is_main is stale from the previous build — **fixed: per-build state is reset**
- `return None` in a void function is rejected ('None has no Flowgorithm equivalent' / 'unexpected return value') — **fixed (C23)**
- Syntax error inside a string annotation is reported at line 1 of the file instead of the annotation's line — **fixed: reported at the annotation**
- f-string `=` specifier (`f"{x=}"`) is rejected with a misleading '!r / !a conversions' message; `f"{x:}"` rejected as 'nested format specs' — **fixed for numbers; `{x:}` works**
- Bare `main()` call at module level (no __name__ guard) gets the generic 'module-level code is not supported' error with a hint that does not apply — **fixed: accepted as the entry call**
- `while 1:` with a trailing `if cond: break` is not recognised as the Do-loop pattern (only `while True:` is) — **fixed (batch 1)**
- Launcher module that imports main (`from game import main` + guard) is reported as 'no main() function and no module-level code found' — **fixed**
- Loop variable re-used as a float element variable makes the For counter Real (silently; only fprg_lint warns) — **converted: that loop counts with a hidden counter**
- Array created inside a loop body emits a Declare that re-executes every iteration (only fprg_lint warns) — **a converter warning (by design)**
- `yield` in a reachable function is reported as 'expression statement has no effect' — **fixed: 'generators (yield) are not supported'**
- Unannotated nested list `[[0] * 3] * 3` gets 'cannot infer the element type' with a hint to annotate `list[int]` — **fixed: 'nested lists are not supported'**
- Starred call argument `add(*xs)` is reported as an arity error ('expects 2 arguments, got 1') — **fixed: '*args in calls is not supported'**
- return inside an elif branch is silently turned into an assignment; the code after the if-chain still runs (value and void functions) — **fixed (C18)**
- return nested inside an if within another if is silently dropped as an early exit (code after the outer if runs, wrong value returned) — **fixed (C17)**
- // with a negative operand that is not a literal gives truncated instead of floored results (temperature table with negative Celsius) — **converted (C1)**
- % with a negative dividend from a variable keeps the dividend's sign (Caesar decrypt wraps to '^', odd test fails) with no warning — **converted (C2)**
- Chained comparison duplicates the middle operand, so a call with side effects (input prompt, print, Random) is executed twice — **converted (C0)**
- Unannotated parameter is typed Integer from one literal call site; a Real argument at another call site is silently truncated — **fixed (C20)**
- A Real argument passed to an int-annotated parameter is silently truncated (Python ignores the annotation and prints the Real) — **fixed: a clean error**
- Module-level program: a function reading a module variable that is reassigned later gets the last literal value for every call — **fixed: a clean error**
- Statements other than main() inside the `if __name__ == "__main__":` guard are silently dropped — **converted: such a block becomes Main, main() an ordinary function**
- input() assigned to an array element is rejected with a misleading message ("must be assigned directly to a variable") — **fixed (batch 1)**
