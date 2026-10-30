"""Interactive prompts built only from input()/print(), so they map to Flowgorithm Input/Output."""


def ask_int(prompt: str, low: int, high: int) -> int:
    """Ask until the player types a whole number between low and high (inclusive)."""
    value = int(input(prompt))
    while value < low or value > high:
        print(f"Please enter a number from {low} to {high}.")
        value = int(input(prompt))
    return value


def ask_yes_no(prompt: str) -> bool:
    """Ask a yes/no question until the answer starts with y, Y, n or N."""
    while True:
        answer = input(prompt)
        if is_yes_or_no(answer):
            break
    return is_yes(answer)


def is_yes(answer: str) -> bool:
    """True when the answer starts with y or Y."""
    if len(answer) == 0:
        return False
    first = answer[0]
    return first == "y" or first == "Y"


def is_yes_or_no(answer: str) -> bool:
    """True when the answer starts with y, Y, n or N."""
    if len(answer) == 0:
        return False
    first = answer[0]
    return first == "y" or first == "Y" or first == "n" or first == "N"
