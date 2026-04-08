"""
Smart LLM Router — routes tasks to Ollama (free) or Claude (paid)
based on complexity analysis.

Strategy:
  - Simple tasks (classify, summarize, format, lookup) → Ollama
  - Complex tasks (code, strategy, analysis, creative) → Claude
  - Rule-based tasks (status check, data fetch) → No LLM needed
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger("llm.router")

# ── Complexity signals ────────────────────────────────────────────────

_COMPLEX_KEYWORDS = [
    "code", "implement", "develop", "refactor", "debug", "fix bug",
    "write function", "build", "architect", "design system",
    "strategy", "analyze", "deep analysis", "competitor",
    "financial model", "forecast", "budget allocation",
    "creative concept", "campaign strategy", "ad copy",
    "review code", "security audit", "deploy",
    "write test", "integration", "api design",
]

_SIMPLE_KEYWORDS = [
    "summarize", "classify", "categorize", "extract", "format",
    "translate", "list", "count", "describe briefly",
    "what is", "define", "explain simply",
    "status", "check", "verify", "confirm",
]

_RULE_BASED_KEYWORDS = [
    "health check", "ping", "fetch data", "pull metrics",
    "sync", "refresh", "upload", "download",
    "get status", "list files", "count records",
]


def estimate_complexity(task_type: str, description: str) -> str:
    """Estimate task complexity. Returns 'complex', 'simple', or 'rule_based'."""
    text = f"{task_type} {description}".lower()

    # Check rule-based first (no LLM needed)
    if any(kw in text for kw in _RULE_BASED_KEYWORDS):
        return "rule_based"

    # Check complex signals
    complex_score = sum(1 for kw in _COMPLEX_KEYWORDS if kw in text)
    simple_score = sum(1 for kw in _SIMPLE_KEYWORDS if kw in text)

    # Length heuristic: longer descriptions tend to be more complex
    if len(description) > 200:
        complex_score += 1

    if complex_score > simple_score:
        return "complex"
    elif simple_score > 0:
        return "simple"

    # Default: treat as complex to be safe
    return "complex"


def route_task(task_type: str, description: str) -> str:
    """Route a task to the appropriate LLM provider.

    Returns:
        'claude'  — use Claude Sonnet (complex tasks, code, strategy)
        'ollama'  — use Ollama local (simple tasks, summaries)
        'none'    — no LLM needed (rule-based execution)
    """
    complexity = estimate_complexity(task_type, description)

    if complexity == "rule_based":
        return "none"
    elif complexity == "simple":
        # Check if Ollama is available
        if _is_ollama_available():
            return "ollama"
        else:
            return "claude"  # fallback to Claude if Ollama is down
    else:
        return "claude"


def _is_ollama_available() -> bool:
    """Quick check if Ollama server is responding."""
    try:
        import urllib.request
        url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        base = url.rstrip("/v1").rstrip("/")
        urllib.request.urlopen(f"{base}/api/tags", timeout=2)
        return True
    except Exception:
        return False


class LLMRouter:
    """Stateful router that manages provider selection and token tracking."""

    def __init__(self):
        self._token_usage = {"claude": 0, "ollama": 0}
        self._call_count = {"claude": 0, "ollama": 0}

    def route(self, task_type: str, description: str) -> str:
        return route_task(task_type, description)

    def complete(self, prompt: str, system: str = "",
                 task_type: str = "default", description: str = "",
                 max_tokens: int = 4096, temperature: float = 0.7) -> str:
        """Route and execute an LLM completion."""
        provider = self.route(task_type, description)

        if provider == "none":
            return ""

        try:
            from src.llm.providers import get_llm
            llm = get_llm()

            if provider == "ollama" and _is_ollama_available():
                # Force Ollama by temporarily overriding
                result = self._call_ollama(prompt, system, max_tokens, temperature)
                if result:
                    self._token_usage["ollama"] += len(result) // 4
                    self._call_count["ollama"] += 1
                    return result

            # Default: use FallbackLLM (tries Anthropic first)
            result = llm.complete(
                prompt=prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self._token_usage["claude"] += len(result) // 4
            self._call_count["claude"] += 1
            return result

        except Exception as exc:
            logger.exception("LLM call failed: %s", exc)
            return f"[LLM Error] {exc}"

    def _call_ollama(self, prompt: str, system: str,
                     max_tokens: int, temperature: float) -> Optional[str]:
        """Direct Ollama call."""
        try:
            import json
            import urllib.request

            base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/v1").rstrip("/")
            model = os.getenv("OLLAMA_MODEL", "llama3")

            payload = json.dumps({
                "model": model,
                "prompt": f"{system}\n\n{prompt}" if system else prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }).encode()

            req = urllib.request.Request(
                f"{base}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=60)
            data = json.loads(resp.read())
            return data.get("response", "")

        except Exception as exc:
            logger.warning("Ollama call failed, falling back: %s", exc)
            return None

    def get_stats(self) -> dict:
        return {
            "token_usage": dict(self._token_usage),
            "call_count": dict(self._call_count),
            "ollama_available": _is_ollama_available(),
        }
