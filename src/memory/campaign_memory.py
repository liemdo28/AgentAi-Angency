"""
Campaign Memory — event log per campaign.
Tracks milestones, A/B test results, creative rotations, budget changes, and KPI snapshots.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db.connection import get_db

logger = logging.getLogger(__name__)

CAMPAIGN_EVENT_TYPES = (
    "launch",
    "pause",
    "budget_change",
    "creative_rotation",
    "a_b_test_result",
    "kpi_snapshot",
    "targeting_change",
    "sla_breach",
    "escalation",
    "human_review",
    "task_completed",
    "review_failed",
    "retry",
    "general",
)


class CampaignMemoryStore:
    """Persist and retrieve event log for a specific campaign."""

    def __init__(self, campaign_id: str) -> None:
        self.campaign_id = campaign_id

    # ── Write ──────────────────────────────────────────────────────────

    def log_event(
        self,
        event_type: str,
        description: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        """Record a campaign event. Returns the event_id."""
        if event_type not in CAMPAIGN_EVENT_TYPES:
            raise ValueError(f"Unknown event_type: {event_type}")

        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        meta = json.dumps(metadata or {})

        cursor = db.execute(
            """
            INSERT INTO campaign_memory
              (campaign_id, event_type, description, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (self.campaign_id, event_type, description, meta, now),
        )
        db.commit()
        logger.debug("Event %d logged for campaign %s", cursor.lastrowid, self.campaign_id)
        return int(cursor.lastrowid)

    def snapshot_kpis(self, kpi_data: dict[str, float]) -> int:
        """Convenience: store a KPI snapshot."""
        return self.log_event(
            event_type="kpi_snapshot",
            description=f"KPI snapshot: {kpi_data}",
            metadata={"kpis": kpi_data},
        )

    def log_review_result(self, task_id: str, passed: bool, score: float) -> int:
        """Convenience: log leader review result."""
        return self.log_event(
            event_type="review_failed" if not passed else "task_completed",
            description=f"Task {task_id} review: {'PASSED' if passed else 'FAILED'} (score={score:.1f})",
            metadata={"task_id": task_id, "passed": passed, "score": score},
        )

    # ── Read ───────────────────────────────────────────────────────────

    def get_events(
        self,
        event_type: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve campaign events, newest first."""
        db = get_db()
        if event_type:
            rows = db.execute(
                """
                SELECT id, event_type, description, metadata, created_at
                FROM campaign_memory
                WHERE campaign_id = ? AND event_type = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.campaign_id, event_type, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT id, event_type, description, metadata, created_at
                FROM campaign_memory
                WHERE campaign_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.campaign_id, limit),
            ).fetchall()

        return [
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "description": r["description"],
                "metadata": json.loads(r["metadata"] or "{}"),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_kpi_snapshots(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get the most recent KPI snapshots for trend analysis."""
        return self.get_events(event_type="kpi_snapshot", limit=limit)

    def get_latest_scores(self, limit: int = 5) -> list[dict[str, Any]]:
        """Get the most recent task review scores."""
        events = self.get_events(limit=100)
        scores = []
        for e in events:
            if e["event_type"] in ("task_completed", "review_failed"):
                scores.append(e)
        return scores[:limit]

    def get_timeline(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get the full event timeline for campaign review."""
        return self.get_events(limit=limit)

    def count(self) -> int:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) as n FROM campaign_memory WHERE campaign_id = ?",
            (self.campaign_id,),
        ).fetchone()
        return row["n"] if row else 0
