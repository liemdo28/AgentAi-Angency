"""Ensure the project root is on sys.path so that root-level shim modules
(models, engine, policies, store, etc.) are found first.

NOTE: test_agents.py stubs sys.modules at import time to avoid heavy deps.
Because pytest collects (imports) ALL test files before running any, those
stubs poison modules for every other file in the session.  The only safe
fix is to run test_agents.py in a separate pytest invocation — see the CI
workflow, which does exactly that.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
