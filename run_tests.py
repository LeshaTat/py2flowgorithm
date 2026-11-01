"""Run the tests of all three projects: python3 run_tests.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["library/tests", "converter/tests", "examples/tests", "examples/arith_quiz"]

failed = [suite for suite in SUITES
          if subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", suite], cwd=HERE).returncode]
print("failed: " + ", ".join(failed) if failed else f"all {len(SUITES)} suites passed")
sys.exit(1 if failed else 0)
