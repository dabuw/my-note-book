#!/usr/bin/env python3
"""Run the whole NoteTaker test suite.

Usage:
    python tests/run_all.py

Both suites are plain scripts that exercise the real Flask app through its test
client, so no extra test dependencies are needed -- just the runtime
requirements.
"""

import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SUITES = ["test_permissions.py", "test_llm_integration.py"]

# Keep the child processes unbuffered so their output stays in order.
env = dict(os.environ, PYTHONUNBUFFERED="1")

failed = []
for name in SUITES:
    print()
    print("=" * 74)
    print("RUNNING %s" % name)
    print("=" * 74, flush=True)
    result = subprocess.run([sys.executable, "-u", str(HERE / name)],
                            cwd=str(HERE.parent), env=env)
    if result.returncode != 0:
        failed.append(name)

print()
print("=" * 74)
if failed:
    print("FAILED: %s" % ", ".join(failed))
    sys.exit(1)
print("ALL SUITES PASSED")
