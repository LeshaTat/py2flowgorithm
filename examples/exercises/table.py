"""Tables.

A multiplication table and a temperature table.
"""
from flowgorithm import Input, Output, ToFixed


def main():
    Output("Size of the table?")
    n = Input(int)
    for row in range(1, n + 1):
        for col in range(1, n + 1):
            Output(row * col, "\t", newline=False)
        Output()
    for c in range(-10, 41, 10):
        f = c * 9 / 5 + 32
        Output(c, " C = ", ToFixed(f, 1), " F")


if __name__ == "__main__":
    main()
