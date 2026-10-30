"""Guess the Number.

The classic Flowgorithm example as a single Python file: the computer picks a
number from 1 to 100, the player guesses until it is found.
"""
import random

MAX_NUMBER = 100


def rate(tries: int) -> str:
    """A short verdict for the number of tries needed."""
    if tries <= 5:
        return "Excellent!"
    if tries <= 10:
        return "Good."
    return "Keep practising."


def main():
    secret = random.randint(1, MAX_NUMBER)
    tries = 0
    print(f"I am thinking of a number from 1 to {MAX_NUMBER}.")
    while True:
        guess = int(input("Your guess?"))
        tries += 1
        if guess < secret:
            print("Too low.")
        elif guess > secret:
            print("Too high.")
        if guess == secret:
            break
    print(f"Correct! You needed {tries} tries. {rate(tries)}")


if __name__ == "__main__":
    main()
