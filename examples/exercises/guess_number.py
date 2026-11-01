"""Guess the Number.

The classic Flowgorithm exercise: the computer picks a number from 1 to 100 and the
player guesses until it is found.
"""
from flowgorithm import *

MAX_NUMBER = 100


def rate(tries: int) -> str:
    """A short verdict for the number of tries needed."""
    if tries <= 5:
        verdict = "Excellent!"
    elif tries <= 10:
        verdict = "Good."
    else:
        verdict = "Keep practising."
    return verdict


def main():
    secret = Random(MAX_NUMBER) + 1
    tries = 0
    Output("I am thinking of a number from 1 to ", MAX_NUMBER, ".")
    while True:
        Output("Your guess?")
        guess = Input(int)
        tries = tries + 1
        if guess < secret:
            Output("Too low.")
        elif guess > secret:
            Output("Too high.")
        if guess == secret:
            break
    Output("Correct! You needed ", tries, " tries. ", rate(tries))


if __name__ == "__main__":
    main()
