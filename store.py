"""Compatibility shim for legacy tests/imports.
Alias this module to src.store so monkeypatching attributes (e.g. STATE_FILE)
behaves exactly like the original module.
"""
from src import store as _store
import sys

sys.modules[__name__] = _store
