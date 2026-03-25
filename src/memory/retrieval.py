"""
Memory Retrieval — inject relevant memories into specialist prompts.
Top-N memories per account + campaign event log are prepended to task prompts.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.memory.account_memory import AccountMemoryStore
from src.memory.campaign_memory import CampaignMemoryStore

logger = logging.getLogger(__name__)


class MemoryRetrieval:
    """
    Retrieve relevant memories for a task and format them for prompt injection.

    Usage:
        retrieval = MemoryRetrieval(account_id="acc_123", campaign_id="camp_456")
        prompt_additions = retrieval.get_prompt_context(task_type="creative_brief")
        # then inject into specialist system prompt
    """

    DEFAULT_LIMIT = 5

    def __init__(
        self,
        account_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
    ) -> None:
        self.account_id = account_id
        self.campaign_id = campaign_id
        self._account_mem: Optional[AccountMemoryStore] = (
            AccountMemoryStore(account_id) if account_id else None
        )
        self._campaign_mem: Optional[CampaignMemoryStore] = (
            CampaignMemoryStore(campaign_id) if campaign_id else None
        )

    # ── Public API ────────────────────────────────────────────────────

    def get_prompt_context(
        self,
        task_type: Optional[str] = None,
        account_limit: int = 5,
        campaign_limit: int = 5,
    ) -> str:
        """
        Build a single text block of relevant memories for prompt injection.
        Returns "" if no memories found.
        """
        parts = []

        # Account-level memories
        if self._account_mem:
            account_mems = self._account_mem.get(limit=account_limit)
            if account_mems:
                parts.append("## Account Memory (Long-Term)")
                for m in account_mems:
                    parts.append(
                        f"- [{m['memory_type']}] {m['content']} "
                        f"(importance={m['importance']}, {m['created_at'][:10]})"
                    )

        # Campaign event log
        if self._campaign_mem:
            campaign_events = self._campaign_mem.get_events(limit=campaign_limit)
            if campaign_events:
                parts.append("## Campaign Event Log")
                for e in campaign_events:
                    meta_str = ""
                    if e["metadata"]:
                        meta_str = f" | {e['metadata']}"
                    parts.append(
                        f"- [{e['event_type']}] {e['description']} "
                        f"({e['created_at'][:16]}){meta_str}"
                    )

        # KPI snapshots if available
        if self._campaign_mem:
            kpi_snaps = self._campaign_mem.get_kpi_snapshots(limit=3)
            if kpi_snaps:
                parts.append("## Recent KPI Snapshots")
                for s in kpi_snaps:
                    kpis = s["metadata"].get("kpis", {})
                    parts.append(
                        f"- {s['created_at'][:10]}: "
                        + ", ".join(f"{k}={v}" for k, v in kpis.items())
                    )

        if not parts:
            return ""

        header = (
            "=== PRIOR CONTEXT (Do not repeat in output) ===\n"
            "The following memories are from previous work on this account/campaign.\n"
        )
        return header + "\n".join(parts) + "\n=== END PRIOR CONTEXT ===\n"

    def get_recent_scores(self) -> list[dict[str, Any]]:
        """Get recent task scores for trend analysis."""
        if not self._campaign_mem:
            return []
        return self._campaign_mem.get_latest_scores()

    def get_review_history(
        self,
        account_id: str,
        campaign_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get review history from the DB (cross-campaign)."""
        from src.db.connection import get_db

        db = get_db()
        rows = db.execute(
            """
            SELECT id, task_id, campaign_id, leader_score, passed,
                   quality_breakdown, created_at
            FROM review_history
            WHERE campaign_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (campaign_id or account_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def suggest_retries(self) -> list[str]:
        """
        Look at recent review failures and return specific feedback strings
        that should be re-injected on retry.
        """
        from src.db.connection import get_db

        db = get_db()
        rows = db.execute(
            """
            SELECT leader_feedback
            FROM review_history
            WHERE passed = 0
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()

        suggestions = []
        for r in rows:
            fb = r["leader_feedback"]
            if fb and len(fb) > 10:
                suggestions.append(fb)
        return suggestions
