"""Run the tests of all three projects: python3 run_tests.py

Every suite runs with this repository's library and converter first on the path, so it tests
this clone even when an installed copy (python3 install.py) points somewhere else.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["library/tests", "converter/tests", "examples/tests", "examples/arith_quiz"]
SOURCES = [os.path.join(HERE, "library", "src"), os.path.join(HERE, "converter", "src")]

env = dict(os.environ, PYTHONPATH=os.pathsep.join(SOURCES + [p for p in [os.environ.get("PYTHONPATH")] if p]))
failed = [suite for suite in SUITES
          if subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", suite], cwd=HERE, env=env).returncode]
print("failed: " + ", ".join(failed) if failed else f"all {len(SUITES)} suites passed")
sys.exit(1 if failed else 0)
