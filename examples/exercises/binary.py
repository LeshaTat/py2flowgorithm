"""Binary.

Show a number in base 2.
"""
from flowgorithm import Input, Int, Output, ToString


def to_binary(n: int) -> str:
    if n == 0:
        digits = "0"
    else:
        digits = ""
        while n > 0:
            digits = ToString(n % 2) + digits
            n = Int(n / 2)
    return digits


def main():
    Output("A whole number (0 or more)?")
    n = Input(int)
    Output(n, " is ", to_binary(n), " in binary")


if __name__ == "__main__":
    main()
