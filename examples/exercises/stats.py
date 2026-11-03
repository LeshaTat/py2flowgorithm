"""Statistics.

Read some numbers and show the smallest, the largest, the average and how many are above it.
"""
from flowgorithm import Input, Output, ToFixed


def read_count() -> int:
    """Ask until the count is between 1 and 100."""
    while True:
        Output("How many numbers (1-100)?")
        n = Input(int)
        if n >= 1 and n <= 100:
            break
    return n


def average(values: list[float], n: int) -> float:
    total = 0.0
    for i in range(n):
        total += values[i]
    return total / n


def main():
    n = read_count()
    values = [0.0] * n
    for i in range(n):
        Output("Number ", i + 1, "?")
        values[i] = Input(float)
    smallest = values[0]
    largest = values[0]
    for i in range(1, n):
        if values[i] < smallest:
            smallest = values[i]
        if values[i] > largest:
            largest = values[i]
    mean = average(values, n)
    above = 0
    for i in range(n):
        if values[i] > mean:
            above += 1
    Output("Smallest: ", smallest, ", largest: ", largest)
    Output("Average: ", ToFixed(mean, 2), ", above it: ", above)


if __name__ == "__main__":
    main()
