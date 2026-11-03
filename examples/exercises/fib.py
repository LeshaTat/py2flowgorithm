"""Fibonacci.

The Fibonacci numbers, with a loop and with recursion.
"""
from flowgorithm import Input, Output


def fib(n: int) -> int:
    if n < 2:
        result = n
    else:
        result = fib(n - 1) + fib(n - 2)
    return result


def main():
    Output("How many?")
    count = Input(int)
    a = 0
    b = 1
    for i in range(count):
        Output(a, " ", newline=False)
        nxt = a + b
        a = b
        b = nxt
    Output()
    Output("fib(", count, ") = ", fib(count))


if __name__ == "__main__":
    main()
