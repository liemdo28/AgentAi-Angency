"""
Account Memory — long-term memory per account.
Stores key decisions, preferences, client interactions, and brand guidelines.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db.connection import get_db

logger = logging.getLogger(__name__)

MEMORY_TYPES = (
    "brand_guideline",
    "client_preference",
    "strategy_decision",
    "budget_change",
    "contact_update",
    "competitor_info",
    "market_insight",
    "kpi_review",
    "creative_feedback",
    "general",
)


class AccountMemoryStore:
    """Persist and retrieve long-term memories for a specific account."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id

    # ── Write ──────────────────────────────────────────────────────────

    def add(
        self,
        memory_type: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        importance: int = 5,
    ) -> int:
        """
        Store a memory entry for this account.

        Returns the auto-incremented memory_id.
        """
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory_type: {memory_type}")

        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        meta = json.dumps(metadata or {})

        cursor = db.execute(
            """
            INSERT INTO account_memory
              (account_id, memory_type, content, metadata, importance, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (self.account_id, memory_type, content, meta, importance, now),
        )
        db.commit()
        logger.debug("Memory %d stored for account %s", cursor.lastrowid, self.account_id)
        return int(cursor.lastrowid)

    def update_importance(self, memory_id: int, importance: int) -> None:
        db = get_db()
        db.execute(
            "UPDATE account_memory SET importance = ? WHERE id = ? AND account_id = ?",
            (importance, memory_id, self.account_id),
        )
        db.commit()

    # ── Read ───────────────────────────────────────────────────────────

    def get(
        self,
        memory_type: Optional[str] = None,
        limit: int = 10,
        min_importance: int = 1,
    ) -> list[dict[str, Any]]:
        """Retrieve memories, optionally filtered by type."""
        db = get_db()
        if memory_type:
            rows = db.execute(
                """
                SELECT id, memory_type, content, metadata, importance, created_at
                FROM account_memory
                WHERE account_id = ? AND memory_type = ? AND importance >= ?
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (self.account_id, memory_type, min_importance, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT id, memory_type, content, metadata, importance, created_at
                FROM account_memory
                WHERE account_id = ? AND importance >= ?
                ORDER BY importance DESC, created_at DESC
                LIMIT ?
                """,
                (self.account_id, min_importance, limit),
            ).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "memory_type": r["memory_type"],
                "content": r["content"],
                "metadata": json.loads(r["metadata"] or "{}"),
                "importance": r["importance"],
                "created_at": r["created_at"],
            })
        return results

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Full-text search across account memories."""
        db = get_db()
        rows = db.execute(
            """
            SELECT id, memory_type, content, metadata, importance, created_at
            FROM account_memory
            WHERE account_id = ? AND content LIKE ?
            ORDER BY importance DESC, created_at DESC
            LIMIT ?
            """,
            (self.account_id, f"%{query}%", limit),
        ).fetchall()
        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "memory_type": r["memory_type"],
                "content": r["content"],
                "metadata": json.loads(r["metadata"] or "{}"),
                "importance": r["importance"],
                "created_at": r["created_at"],
            })
        return results

    def count(self) -> int:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) as n FROM account_memory WHERE account_id = ?",
            (self.account_id,),
        ).fetchone()
        return row["n"] if row else 0
