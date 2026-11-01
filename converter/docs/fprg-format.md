# Flowgorithm `.fprg` file format (reverse-engineered reference)

Flowgorithm (http://www.flowgorithm.org) stores flowcharts as plain XML in `.fprg`
files. The format is not officially documented; everything below was derived from
real files saved by Flowgorithm 1.0 (2014), 1.7, 2.6, 2.11, 3.0 (2023) and 4.2
(saved by Flowgorithm 4.x in 2024-2026), from the FlowgorithmJS viewer's parser,
and from the official language documentation (operators, intrinsic functions,
keywords, data types).

Current application version: 4.5 (October 2024). Files written by 4.x carry
`fileversion="4.2"`. The statement structure has been stable since 2.x; the only
additions since 2.6 are `direction` on `<for>` and `newline` on `<output>`.

## Skeleton

```xml
<?xml version="1.0"?>
<flowgorithm fileversion="3.0">
    <attributes>
        <attribute name="name" value="Program title"/>
        <attribute name="authors" value="who"/>
        <attribute name="about" value="free text"/>
        <attribute name="saved" value="2024-04-07 01:04:53 PM"/>
        <attribute name="created" value="BASE64"/>   <!-- optional, informational -->
        <attribute name="edited" value="BASE64"/>    <!-- optional, may repeat -->
    </attributes>
    <function name="Main" type="None" variable="">
        <parameters/>
        <body>
            ...statements...
        </body>
    </function>
    <function name="Circle" type="Real" variable="Area">
        <parameters>
            <parameter name="Radius" type="Real" array="False"/>
        </parameters>
        <body>
            <declare name="Area" type="Real" array="False" size=""/>
            <assign variable="Area" expression="Pi * Radius ^ 2"/>
        </body>
    </function>
</flowgorithm>
```

* No `encoding` declaration; files are ASCII with numeric character references
  (`&#193;`) for non-ASCII characters. Line endings are LF, indentation 4 spaces.
* `created`/`edited` are base64 of `user;machine;date;time;count`. They are
  bookkeeping only; 1.x files do not have them and still load.
* Every program has exactly one `Main` function (`type="None" variable=""`).
* A function's return value is **the value of the variable named in `variable`
  when the function ends**. There is no return statement. The return variable is
  declared in the body like any other variable (real files always do this).
* `type` is one of `None`, `Integer`, `Real`, `String`, `Boolean`.
* Identifiers are case-insensitive.

## Statements (children of `<body>`, `<then>`, `<else>`, `<while>`, `<for>`, `<do>`)

| Element | Attributes | Notes |
|---|---|---|
| `<declare name="a, b" type="Integer" array="False" size=""/>` | name, type, array, size | Several scalars may share one declare (comma separated). Arrays: `array="True" size="<expr>"`, one name. 1.0 files used `variables=` instead of `name=`. |
| `<assign variable="x" expression="x + 1"/>` | variable, expression | `variable` may be an element: `arr[i]` |
| `<input variable="x"/>` | variable | Reads keyboard into variable; converted to the variable's type. No prompt (use an output first). |
| `<output expression="&quot;Hi &quot; &amp; name" newline="True"/>` | expression, newline | newline `True`/`False` |
| `<if expression="x &gt; 5"><then>…</then><else>…</else></if>` | expression | Both `<then>` and `<else>` are always present, possibly empty (`<else/>`). |
| `<while expression="n &lt;= 100">…</while>` | expression | Pre-test loop |
| `<do expression="age &lt; 0 or age &gt; 110">…</do>` | expression | Post-test loop: body runs, then loops **while** expression is true |
| `<for variable="i" start="0" end="n - 1" direction="inc" step="1">…</for>` | variable, start, end, direction, step | `end` is **inclusive**. `direction` is `inc` or `dec`; `step` is a positive expression. Old files omit `direction`. |
| `<call expression="Greeting(name)"/>` | expression | Call a `None`-typed function (statement). Value-returning functions are used inside expressions. |
| `<comment text="…"/>` | text | Multi-line text uses `&#13;&#10;` |
| `<breakpoint/>` | – | Pauses execution |

Flowgorithm 3.x/4.x also has Turtle Graphics shapes (`forward`, `turn`, `pen`,
`home`, `clear`) and file shapes (`open`, `close`, `read`, `write`). Their
attributes were not observed in sample files and are not emitted by the converter.

## Expression language

Literals: integers `42`, reals `3.14`, strings in double quotes `"text"`,
booleans `true`/`false`, constant `pi` (or `π`).

Operators (C family / BASIC family / Unicode are interchangeable), precedence
high to low:

| Level | Operators |
|---|---|
| 8 unary | `-`  `!`  `not`  `¬` |
| 7 exponent | `^`  `↑` |
| 6 multiplicative | `*` `×` `/` `÷` `%` `mod` (division is always floating point) |
| 5 additive | `+` `-` (`+` works only on numbers) |
| 4 concatenation | `&` (string concatenation; converts numbers to text) |
| 3 relational | `>` `<` `>=` `≥` `<=` `≤` `==` `=` `!=` `<>` `≠` |
| 2 logical and | `and` `&&` `∧` |
| 1 logical or | `or` `||` `∨` |

Arrays are 0-based and indexed with `a[i]`. Function calls: `Name(arg, arg)`.

Intrinsic functions: `Abs Arcsin Arccos Arctan Cos Int Ln Log Log10 Sgn Sin Sqrt Tan`
(math), `Len(s) Char(s, i)` (strings, 0-based), `ToChar ToCode ToFixed(r, i)
ToInteger ToReal ToString` (conversion), `EOF() Random(n) Size(a)`.
`Random(n)` returns an integer in `0 .. n-1`. `Int(n)` truncates a real.

Identifiers: start with a letter, then letters or digits, **no underscores**,
case-insensitive, and must not be a reserved word: `and false mod not or pi true`,
the type names `boolean integer real string`, any intrinsic function name, or
the reserved-for-future names `arccosh cosh arcsinh sinh arctanh tanh`.

Semantics worth knowing for code generation:

* Integer to Real assignment converts implicitly; Real to Integer truncates.
* `+` never concatenates: use `&` for strings. `&` accepts any operand types.
* `/` always yields a Real; integer division is `Int(a / b)`.
* Variables are function-local. There are no globals; Main's variables are not
  visible in other functions. Pass them as parameters.
* Arrays are declared with a size expression and have fixed size.
