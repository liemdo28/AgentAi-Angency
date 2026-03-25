"""Bridge test so `python -m unittest discover` can execute pytest-style suites.

The existing test modules use pytest function tests + fixtures.
`unittest discover` cannot execute those directly (it reports NO TESTS RAN).
This bridge exposes one unittest TestCase that runs pytest internally.
"""
from __future__ import annotations

import unittest

import pytest


class PytestBridgeTest(unittest.TestCase):
    def test_pytest_suites(self) -> None:
        exit_code = pytest.main(
            [
                "-q",
                "tests/test_engine.py",
                "tests/test_store.py",
                "tests/test_validator.py",
            ]
        )
        self.assertEqual(exit_code, 0, f"pytest suite failed with exit code {exit_code}")
