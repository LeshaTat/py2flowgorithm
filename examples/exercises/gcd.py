"""Greatest common divisor.

Euclid's algorithm, with a loop and with recursion.
"""
from flowgorithm import Input, Int, Output


def gcd(a: int, b: int) -> int:
    while b != 0:
        r = a % b
        a = b
        b = r
    return a


def gcd_recursive(a: int, b: int) -> int:
    if b == 0:
        result = a
    else:
        result = gcd_recursive(b, a % b)
    return result


def main():
    Output("Two numbers?")
    a = Input(int)
    b = Input(int)
    Output("gcd = ", gcd(a, b), " = ", gcd_recursive(a, b))
    Output("lcm = ", Int(a * b / gcd(a, b)))


if __name__ == "__main__":
    main()
