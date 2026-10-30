"""Arithmetic Quiz.

An interactive arithmetic quiz: the player chooses how many questions to answer,
solves random addition, subtraction and multiplication problems and gets a grade.
The program only uses input()/print() and plain functions, so py2fprg can turn
it into a Flowgorithm flowchart; the unit tests in tests/ stay in Python.
"""
import random

from prompts import ask_int, ask_yes_no
from questions import (ADD, SUBTRACT, correct_answer, grade, percentage, plural,
                       question_text)

MAX_QUESTIONS = 10
MAX_NUMBER = 12


def main():
    print("Welcome to the arithmetic quiz!")
    name = input("What is your name?")
    play = True
    while play:
        count = ask_int(f"How many questions, {name}? (1-{MAX_QUESTIONS})", 1, MAX_QUESTIONS)
        score = play_round(count)
        percent = percentage(score, count)
        print(f"{name}, you scored {plural(score, 'point')} out of {count} ({percent}%).")
        print(f"Your grade: {grade(percent)}")
        play = ask_yes_no("Play again? (y/n)")
    print("Goodbye!")


def play_round(count: int) -> int:
    """Ask `count` random questions and return the number of correct answers."""
    results = [False] * count  # which questions were answered correctly
    score = 0
    for i in range(count):
        kind = random.randint(ADD, SUBTRACT)
        a = random.randint(1, MAX_NUMBER)
        b = random.randint(1, MAX_NUMBER)
        answer = ask_int(f"Question {i + 1}: {question_text(kind, a, b)}", -1000, 1000)
        if answer == correct_answer(kind, a, b):
            print("Correct!")
            results[i] = True
            score += 1
        else:
            print(f"Sorry, the answer is {correct_answer(kind, a, b)}.")
    show_summary(results)
    return score


def show_summary(results: list[bool]):
    """Print one line with a star for every correct answer and a dash for a wrong one."""
    line = ""
    for ok in results:
        if ok:
            line = line + "*"
        else:
            line = line + "-"
    print("Results: " + line)


# fg: ignore
def summary_string(results: list[bool]) -> str:
    """Test helper: same picture as show_summary(), returned instead of printed.

    Ignored by py2fprg (see the directive above), so it may use any Python feature.
    """
    return "".join("*" if ok else "-" for ok in results)


if __name__ == "__main__":
    main()
