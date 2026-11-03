"""Bubble sort.

Read numbers into an array, sort them and print them.
"""
from flowgorithm import Input, Output

COUNT = 5


def main():
    numbers = [0] * COUNT
    for i in range(COUNT):
        Output("Number ", i + 1, "?")
        numbers[i] = Input(int)
    # sort: the largest value bubbles to the end in every pass
    for done in range(COUNT - 1):
        for i in range(COUNT - 1 - done):
            if numbers[i] > numbers[i + 1]:
                temp = numbers[i]
                numbers[i] = numbers[i + 1]
                numbers[i + 1] = temp
    for i in range(COUNT):
        Output(numbers[i])


if __name__ == "__main__":
    main()
