"""Run the converter from this checkout without installation.

Usage: python3 py2fprg.py program.py
"""
from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent / "converter" / "src"))
    from py2fprg.cli import main

    sys.exit(main())
