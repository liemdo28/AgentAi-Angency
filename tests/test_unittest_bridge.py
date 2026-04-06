"""Bridge test so `python -m unittest discover` can execute pytest-style suites.

The existing test modules use pytest function tests + fixtures.
`unittest discover` cannot execute those directly (it reports NO TESTS RAN).
This bridge exposes one unittest TestCase that runs pytest internally.
"""
from __future__ import annotations

import subprocess
import sys
import unittest


class PytestBridgeTest(unittest.TestCase):
    def test_pytest_suites(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_engine.py",
                "tests/test_store.py",
                "tests/test_validator.py",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"pytest suite failed with exit code {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}",
        )
