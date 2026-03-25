"""Compatibility shim for legacy tests/imports.
Re-export WorkflowEngine from src.engine.
"""
from src.engine import WorkflowEngine

__all__ = ["WorkflowEngine"]
