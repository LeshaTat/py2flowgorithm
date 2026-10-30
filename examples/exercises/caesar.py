"""Caesar cipher.

Shift every letter of a message by a key.
"""
from flowgorithm import *


def shift(c: str, key: int) -> str:
    code = ToCode(c)
    if code >= ToCode("a") and code <= ToCode("z"):
        result = ToChar((code - ToCode("a") + key) % 26 + ToCode("a"))
    elif code >= ToCode("A") and code <= ToCode("Z"):
        result = ToChar((code - ToCode("A") + key) % 26 + ToCode("A"))
    else:
        result = c
    return result


def encode(message: str, key: int) -> str:
    secret = ""
    for i in range(Len(message)):
        secret = secret + shift(Char(message, i), key)
    return secret


def main():
    Output("Message?")
    message = Input(str)
    Output("Key (1-25)?")
    key = Input(int)
    secret = encode(message, key)
    Output("Encoded: ", secret)
    Output("Decoded: ", encode(secret, 26 - key))


if __name__ == "__main__":
    main()
