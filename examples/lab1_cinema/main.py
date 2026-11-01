"""Cinema Seats.

Lab 1 (Grade 9, Flowgorithm arrays). A small cinema has 10 seats, numbered 1 to 10. The Boolean
array booked says which seats are taken (seat 1 is at index 0); seats 2, 5 and 7 are booked at
the start. A menu shows the seats until the user quits.
"""
# This file is the program, a menu; each task has a file of its own, with its tests next to its
# functions: task 1.1 is in task_1_1.py. Run them all with: python3 -m unittest discover -p "*.py"
import unittest

from flowgorithm import *
from task_1_1 import SEATS, book, show_map

# the menu
SHOW = 1
QUIT = 2


def read_number(prompt: str, low: int, high: int, complaint: str) -> int:
    """Ask until the answer is a number from low to high, saying `complaint` after each other one."""
    Output(prompt)
    number = Input(int)
    while number < low or number > high:
        Output(complaint)
        number = Input(int)
    return number


def show_menu():
    Output("1 Show seats")
    Output("2 Quit")


def main():
    booked = [False] * SEATS
    # at the start seats 2, 5 and 7 are booked
    book(booked, 2)
    book(booked, 5)
    book(booked, 7)
    while True:
        show_menu()
        choice = read_number("Choice?", SHOW, QUIT, "Invalid choice")
        if choice == SHOW:
            show_map(booked)
        if choice == QUIT:
            break
    Output("Goodbye")


if __name__ == "__main__":
    main()


class MenuTest(unittest.TestCase):
    MENU = "1 Show seats\n2 Quit\nChoice?\n"
    START_MAP = "0:- 1:X 2:- 3:- 4:X 5:- 6:X 7:- 8:- 9:-"
    SESSIONS = [  # typed answers: each session is also played as the flowchart
        ["2"],
        ["1", "2"],
        ["0", "3", "1", "1", "2"],
    ]

    @staticmethod
    def play(*answers: str) -> str:
        with console(*answers) as screen:
            main()
        return screen.text

    def test_quit(self):
        self.assertEqual(self.play("2"), self.MENU + "Goodbye\n")

    def test_show_seats(self):
        self.assertEqual(self.play("1", "2"), self.MENU + self.START_MAP + "\n" + self.MENU + "Goodbye\n")

    def test_invalid_choice(self):
        self.assertEqual(self.play("0", "3", "2"), self.MENU + "Invalid choice\nInvalid choice\nGoodbye\n")

    def test_read_number_asks_again(self):
        with console("0", "11", "3") as screen:
            number = read_number("Seat?", 1, 10, "Invalid seat")
        self.assertEqual(number, 3)
        self.assertEqual(screen.text, "Seat?\nInvalid seat\nInvalid seat\n")


class FlowchartTest(unittest.TestCase):
    """The flowchart prints what the Python program prints (needs the py2fprg converter)."""

    def test_python_and_flowchart_print_the_same(self):
        import os
        import fprg_lint
        import fprg_run
        from py2fprg import convert_file
        xml = convert_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), metadata=False)
        self.assertEqual([f for f in fprg_lint.lint_string(xml, "main") if f.severity == "ERROR"], [])
        for answers in MenuTest.SESSIONS:
            with self.subTest(answers=answers):
                self.assertEqual(MenuTest.play(*answers), fprg_run.run_string(xml, answers))

    def test_the_flowchart_is_up_to_date(self):
        import os
        import re
        from py2fprg import convert_file
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "main.fprg"), encoding="utf-8") as fh:
            saved = fh.read()

        def without_attributes(xml: str) -> str:
            return re.sub(r"\s*<attribute [^>]*/>", "", xml)

        self.assertEqual(without_attributes(saved), without_attributes(convert_file(os.path.join(here, "main.py"))),
                         "regenerate it: py2fprg main.py")
