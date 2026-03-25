"""Compatibility shim for legacy tests/imports.
Alias submodule to keep shared module state.
"""
from src.policies import validator as _mod
import sys

sys.modules[__name__] = _mod
