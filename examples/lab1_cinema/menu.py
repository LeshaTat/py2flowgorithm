"""The menu, and asking for a number until it is in range."""
import unittest

from flowgorithm import *

# the menu
SHOW = 1
QUIT = 2


def show_menu():
    Output("1 Show seats")
    Output("2 Quit")


def read_number(prompt: str, low: int, high: int, complaint: str) -> int:
    """Ask until the answer is a number from low to high, saying `complaint` after each other one."""
    Output(prompt)
    number = Input(int)
    while number < low or number > high:
        Output(complaint)
        number = Input(int)
    return number


def read_choice() -> int:
    """Show the menu and ask until the choice is one of its options."""
    show_menu()
    return read_number("Choice?", SHOW, QUIT, "Invalid choice")


class MenuTest(unittest.TestCase):
    def test_read_number_asks_again(self):
        with console("0", "11", "3") as screen:
            number = read_number("Seat?", 1, 10, "Invalid seat")
        self.assertEqual(number, 3)
        self.assertEqual(screen.text, "Seat?\nInvalid seat\nInvalid seat\n")

    def test_read_choice(self):
        with console("0", "3", "2") as screen:
            choice = read_choice()
        self.assertEqual(choice, QUIT)
        self.assertEqual(screen.text, "1 Show seats\n2 Quit\nChoice?\nInvalid choice\nInvalid choice\n")
