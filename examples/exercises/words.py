"""Word count.

Count the words of a sentence and find the longest one.
"""
from flowgorithm import Char, Input, Len, Output


def main():
    Output("A sentence?")
    text = Input(str)
    words = 0
    longest = ""
    current = ""
    for i in range(Len(text) + 1):
        if i < Len(text):
            c = Char(text, i)
        else:
            c = " "
        if c == " ":
            if Len(current) > 0:
                words += 1
                if Len(current) > Len(longest):
                    longest = current
            current = ""
        else:
            current = current + c
    Output(words, " words; the longest is '", longest, "'")


if __name__ == "__main__":
    main()
