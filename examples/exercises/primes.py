"""Prime numbers.

List the prime numbers up to a limit.
"""
from flowgorithm import *


def is_prime(n: int) -> bool:
    """True when n has no divisor other than 1 and itself."""
    prime = n >= 2
    d = 2
    while prime and d * d <= n:
        if n % d == 0:
            prime = False
        d += 1
    return prime


def main():
    Output("Up to?")
    limit = Input(int)
    count = 0
    for n in range(2, limit + 1):
        if is_prime(n):
            Output(n, " ", newline=False)
            count += 1
    Output()
    Output(count, " primes")


if __name__ == "__main__":
    main()
