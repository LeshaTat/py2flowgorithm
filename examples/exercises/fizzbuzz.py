"""FizzBuzz.

Print the numbers from 1 to n; multiples of 3 are Fizz, of 5 Buzz, of both FizzBuzz.
"""
from flowgorithm import *


def main():
    Output("How far?")
    n = Input(int)
    for i in range(1, n + 1):
        if i % 15 == 0:
            Output("FizzBuzz")
        elif i % 3 == 0:
            Output("Fizz")
        elif i % 5 == 0:
            Output("Buzz")
        else:
            Output(i)


if __name__ == "__main__":
    main()
