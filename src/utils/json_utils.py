"""Utility: robust JSON extraction from LLM raw output."""
from __future__ import annotations

import json
import re
from typing import Any


def extract_first_json_object(text: str) -> dict[str, Any]:
    """
    Extract the first JSON object from an LLM raw response.
    Handles common LLM formatting issues:
    - JSON wrapped in markdown code fences (```json ... ```)
    - JSON with leading/trailing whitespace
    - Truncated JSON (tries to repair common issues)
    - Multiple JSON objects (returns the first)
    Returns an empty dict if nothing valid is found.
    """
    if not text or not text.strip():
        return {}

    text = text.strip()

    # 1. Strip markdown code fences
    fence_pattern = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE | re.MULTILINE)
    match = fence_pattern.match(text)
    if match:
        text = match.group(1).strip()

    # 2. Try direct parse
    try:
        return dict(json.loads(text))
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Extract first {...} block
    brace_pattern = re.compile(r"\{[\s\S]+?\}")
    match = brace_pattern.search(text)
    if match:
        candidate = match.group()
        try:
            return dict(json.loads(candidate))
        except (json.JSONDecodeError, TypeError):
            pass

    # 4. Try to fix common truncation issues (missing closing braces)
    # If the text looks like it starts with { but is truncated, try to fix
    if text.startswith("{"):
        # Try appending } to close the object
        for closing in ["}", "}]", "}}", "}}]"]:
            try:
                return dict(json.loads(text + closing))
            except (json.JSONDecodeError, TypeError):
                continue

    # 5. Extract key-value pairs manually as last resort
    result: dict[str, Any] = {}
    kv_pattern = re.compile(r'"(\w+)":\s*("([^"\\]|\\.)*"|[\d.]+|true|false|null|\{[\s\S]*?\})')
    for key_match, val_match in kv_pattern.findall(text):
        val = val_match.group() if hasattr(val_match, "group") else val_match
        try:
            result[key_match] = json.loads(val)
        except (json.JSONDecodeError, TypeError):
            # Strip quotes for string values
            result[key_match] = val.strip('"')
    if result:
        return result

    return {}
