"""Task 1.1: the seats and the seat map.

A small cinema has SEATS seats, numbered from 1; seat 1 is at index 0. The Boolean array booked
says which seats are taken.
"""
import unittest

from flowgorithm import *

SEATS = 10


def book(booked: list[bool], seat: int):
    booked[seat - 1] = True


def seat_map(booked: list[bool]) -> str:
    """The seats on one line, each as its index, a colon and X (booked) or - (free)."""
    line = ""
    for i in range(SEATS):
        if i > 0:
            line = line + " "
        if booked[i]:
            mark = "X"
        else:
            mark = "-"
        line = line + ToString(i) + ":" + mark
    return line


def show_map(booked: list[bool]):
    Output(seat_map(booked))


class SeatMapTest(unittest.TestCase):
    @staticmethod
    def seats(*taken: int) -> list[bool]:
        booked = [False] * SEATS
        for seat in taken:
            book(booked, seat)
        return booked

    def test_the_start(self):
        self.assertEqual(seat_map(self.seats(2, 5, 7)), "0:- 1:X 2:- 3:- 4:X 5:- 6:X 7:- 8:- 9:-")

    def test_all_free_and_all_booked(self):
        self.assertEqual(seat_map(self.seats()), "0:- 1:- 2:- 3:- 4:- 5:- 6:- 7:- 8:- 9:-")
        self.assertEqual(seat_map(self.seats(*range(1, 11))), "0:X 1:X 2:X 3:X 4:X 5:X 6:X 7:X 8:X 9:X")

    def test_book_takes_a_seat_number(self):
        self.assertEqual(self.seats(3), [False, False, True, False, False, False, False, False, False, False])

    def test_show_map(self):
        with console() as screen:
            show_map(self.seats(1))
        self.assertEqual(screen.text, "0:X 1:- 2:- 3:- 4:- 5:- 6:- 7:- 8:- 9:-\n")
