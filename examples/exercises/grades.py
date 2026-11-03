"""Grades.

Turn scores into letter grades until the user types -1.
"""
from flowgorithm import Input, Output


def letter(score: int) -> str:
    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"
    return grade


def main():
    count = 0
    total = 0
    Output("Score (-1 to stop)?")
    score = Input(int)
    while score != -1:
        Output("Grade: ", letter(score))
        count += 1
        total += score
        Output("Score (-1 to stop)?")
        score = Input(int)
    if count > 0:
        Output("Average: ", total / count)


if __name__ == "__main__":
    main()
