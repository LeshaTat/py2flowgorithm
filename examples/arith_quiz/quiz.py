"""Arithmetic Quiz.

The player chooses how many questions to answer, solves random addition, subtraction
and multiplication problems and gets a grade. test_quiz.py checks the functions and
plays whole games with scripted answers.
"""
from flowgorithm import *

MAX_QUESTIONS = 10
MAX_NUMBER = 12
# kinds of questions
ADD = 1
MULTIPLY = 2
SUBTRACT = 3


def ask_int(low: int, high: int) -> int:
    """Read whole numbers until one is between low and high (inclusive)."""
    value = Input(int)
    while value < low or value > high:
        Output("Please enter a number from ", low, " to ", high, ".")
        value = Input(int)
    return value


def is_yes(answer: str) -> bool:
    """True when the answer starts with y or Y."""
    yes = False
    if Len(answer) > 0:
        first = Char(answer, 0)
        yes = first == "y" or first == "Y"
    return yes


def is_yes_or_no(answer: str) -> bool:
    """True when the answer starts with y, Y, n or N."""
    valid = False
    if Len(answer) > 0:
        first = Char(answer, 0)
        valid = first == "y" or first == "Y" or first == "n" or first == "N"
    return valid


def ask_yes_no() -> bool:
    """Read answers until one starts with y, Y, n or N; true for yes."""
    while True:
        answer = Input(str)
        if is_yes_or_no(answer):
            break
    return is_yes(answer)


def question_text(kind: int, a: int, b: int) -> str:
    """The question as shown to the player, e.g. '7 x 8 = ?'."""
    if kind == ADD:
        sign = " + "
    elif kind == SUBTRACT:
        sign = " - "
    else:
        sign = " x "
    return ToString(a) + sign + ToString(b) + " = ?"


def correct_answer(kind: int, a: int, b: int) -> int:
    """The right answer for a question."""
    if kind == ADD:
        answer = a + b
    elif kind == SUBTRACT:
        answer = a - b
    else:
        answer = a * b
    return answer


def percentage(score: int, total: int) -> int:
    """Whole-number percentage of correct answers (0 when nothing was asked)."""
    percent = 0
    if total > 0:
        percent = Int(score * 100 / total)
    return percent


def grade(percent: int) -> str:
    """Letter grade for a percentage."""
    if percent >= 90:
        letter = "A"
    elif percent >= 75:
        letter = "B"
    elif percent >= 50:
        letter = "C"
    else:
        letter = "F"
    return letter


def plural(count: int, word: str) -> str:
    """'1 point' or '3 points'."""
    text = ToString(count) + " " + word
    if count != 1:
        text = text + "s"
    return text


def show_summary(results: list[bool]):
    """One line with a star for every correct answer and a dash for a wrong one."""
    line = ""
    for i in range(Size(results)):
        if results[i]:
            line = line + "*"
        else:
            line = line + "-"
    Output("Results: ", line)


def play_round(count: int) -> int:
    """Ask `count` random questions; the result is the number of correct answers."""
    results = [False] * count  # which questions were answered correctly
    score = 0
    for i in range(count):
        kind = Random(3) + 1  # ADD, MULTIPLY or SUBTRACT
        a = Random(MAX_NUMBER) + 1
        b = Random(MAX_NUMBER) + 1
        Output("Question ", i + 1, ": ", question_text(kind, a, b))
        answer = ask_int(-1000, 1000)
        if answer == correct_answer(kind, a, b):
            Output("Correct!")
            results[i] = True
            score = score + 1
        else:
            Output("Sorry, the answer is ", correct_answer(kind, a, b), ".")
    show_summary(results)
    return score


def main():
    Output("Welcome to the arithmetic quiz!")
    Output("What is your name?")
    name = Input(str)
    play = True
    while play:
        Output("How many questions, ", name, "? (1-", MAX_QUESTIONS, ")")
        count = ask_int(1, MAX_QUESTIONS)
        score = play_round(count)
        percent = percentage(score, count)
        Output(name, ", you scored ", plural(score, "point"), " out of ", count, " (", percent, "%).")
        Output("Your grade: ", grade(percent))
        Output("Play again? (y/n)")
        play = ask_yes_no()
    Output("Goodbye!")


if __name__ == "__main__":
    main()
