"""Compatibility shim for legacy tests/imports.
Alias submodule so POLICIES mutations are shared with src.policies.*
"""
from src.policies import interdepartment_policies as _mod
import sys

sys.modules[__name__] = _mod
