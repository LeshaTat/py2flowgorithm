"""Menu.

A small calculator driven by a menu.
"""
from flowgorithm import *


def show_menu():
    Output("1) add  2) multiply  3) power  0) quit")


def ask(prompt: str) -> float:
    Output(prompt)
    value = Input(float)
    return value


def main():
    while True:
        show_menu()
        choice = Input(int)
        if choice == 1:
            a = ask("a?")
            b = ask("b?")
            Output(a, " + ", b, " = ", a + b)
        elif choice == 2:
            a = ask("a?")
            b = ask("b?")
            Output(a, " * ", b, " = ", a * b)
        elif choice == 3:
            a = ask("base?")
            b = ask("exponent?")
            Output(a, " ^ ", b, " = ", a ** b)
        elif choice != 0:
            Output("Unknown choice")
        if choice == 0:
            break
    Output("Bye")


if __name__ == "__main__":
    main()
