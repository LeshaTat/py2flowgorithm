"""Cinema Seats.

Lab 1 (Grade 9, Flowgorithm arrays). A small cinema has 10 seats, numbered 1 to 10. The Boolean
array booked says which seats are taken (seat 1 is at index 0); seats 2, 5 and 7 are booked at
the start. A menu shows the seats until the user quits.
"""
# This file is the program. The menu and asking for numbers are in menu.py; each task has a
# file of its own (task 1.1 is in task_1_1.py). Every file has its tests next to its functions:
# run them all with: python3 -m unittest discover -p "*.py"
import unittest

from flowgorithm import *
from menu import QUIT, SHOW, read_choice
from task_1_1 import SEATS, book, show_map


def main():
    booked = [False] * SEATS
    # at the start seats 2, 5 and 7 are booked
    book(booked, 2)
    book(booked, 5)
    book(booked, 7)
    while True:
        choice = read_choice()
        if choice == SHOW:
            show_map(booked)
        if choice == QUIT:
            break
    Output("Goodbye")


if __name__ == "__main__":
    main()


class MainTest(unittest.TestCase):
    MENU = "1 Show seats\n2 Quit\nChoice?\n"
    START_MAP = "0:- 1:X 2:- 3:- 4:X 5:- 6:X 7:- 8:- 9:-"

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
