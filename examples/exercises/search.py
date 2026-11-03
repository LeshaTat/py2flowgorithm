"""Linear search.

Find a value in an array.
"""
from flowgorithm import Input, Output, Size, ToFixed


def main():
    values = [4, 8, 15, 16, 23, 42]
    Output("Find what?")
    wanted = Input(int)
    found = False
    i = 0
    while i < Size(values) and not found:
        if values[i] == wanted:
            found = True
        else:
            i = i + 1
    if found:
        Output(wanted, " is at index ", i)
    else:
        Output(wanted, " is not in the list")
    # the largest value
    largest = values[0]
    for k in range(1, Size(values)):
        if values[k] > largest:
            largest = values[k]
    Output("Largest: ", largest)
    total = 0
    for k in range(Size(values)):
        total += values[k]
    Output("Average: ", ToFixed(total / Size(values), 2))


if __name__ == "__main__":
    main()
