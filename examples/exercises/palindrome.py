"""Palindrome.

Is a word the same backwards?
"""
from flowgorithm import *


def is_palindrome(word: str) -> bool:
    left = 0
    right = Len(word) - 1
    same = True
    while same and left < right:
        if Char(word, left) != Char(word, right):
            same = False
        left = left + 1
        right = right - 1
    return same


def reverse(word: str) -> str:
    result = ""
    for i in range(Len(word) - 1, -1, -1):
        result = result + Char(word, i)
    return result


def main():
    Output("A word?")
    word = Input(str)
    Output(reverse(word))
    if is_palindrome(word):
        Output(word, " is a palindrome")
    else:
        Output(word, " is not a palindrome")


if __name__ == "__main__":
    main()
