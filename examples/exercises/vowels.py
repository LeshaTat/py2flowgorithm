"""Vowels.

Count the (lower-case) vowels in a sentence.
"""
from flowgorithm import Char, Input, Len, Output


def is_vowel(c: str) -> bool:
    return c == "a" or c == "e" or c == "i" or c == "o" or c == "u"


def main():
    Output("A sentence?")
    text = Input(str)
    vowels = 0
    for i in range(Len(text)):
        if is_vowel(Char(text, i)):
            vowels = vowels + 1
    Output(vowels, " vowels out of ", Len(text), " characters")


if __name__ == "__main__":
    main()
