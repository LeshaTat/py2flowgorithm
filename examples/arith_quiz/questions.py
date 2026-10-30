"""Question generation and grading for the arithmetic quiz: pure functions, no I/O."""

# Kinds of questions. Module-level literal constants are copied into every
# Flowgorithm function that uses them (Flowgorithm has no globals).
ADD = 1
MULTIPLY = 2
SUBTRACT = 3


def question_text(kind: int, a: int, b: int) -> str:
    """The question as shown to the player, e.g. '7 x 8 = ?'."""
    if kind == ADD:
        return f"{a} + {b} = ?"
    if kind == SUBTRACT:
        return f"{a} - {b} = ?"
    return f"{a} x {b} = ?"


def correct_answer(kind: int, a: int, b: int) -> int:
    """The right answer for a question."""
    if kind == ADD:
        return a + b
    if kind == SUBTRACT:
        return a - b
    return a * b


def percentage(score: int, total: int) -> int:
    """Whole-number percentage of correct answers (0 when nothing was asked)."""
    if total == 0:
        return 0
    return score * 100 // total


def grade(percent: int) -> str:
    """Letter grade for a percentage."""
    if percent >= 90:
        return "A"
    if percent >= 75:
        return "B"
    if percent >= 50:
        return "C"
    return "F"


def plural(count: int, word: str) -> str:
    """'1 point' or '3 points'."""
    if count == 1:
        return f"{count} {word}"
    return f"{count} {word}s"
