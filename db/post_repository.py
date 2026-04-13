"""
PostRepository — data access layer for posts, post_versions, and post_review_actions.

Connects to the same SQLite WAL database as ControlPlaneDB (data/agency.db).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from db.schema_posts import POSTS_SCHEMA

logger = logging.getLogger("db.posts")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "agency.db"


class PostRepository:
    """Thin repository over posts, post_versions, and post_review_actions tables."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._ensure_schema()

    # ── connection helpers ─────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            conn.executescript(POSTS_SCHEMA)
            conn.commit()
            logger.info("Posts schema ready (%s)", self.db_path)
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return dict(row)

    @staticmethod
    def _decode_json(value: str | None) -> Any:
        try:
            return json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── posts ──────────────────────────────────────────────────────────────────

    def create_post(self, data: dict) -> dict:
        """Insert a new post record. Returns the created row as dict."""
        post_id = data.get("id") or str(uuid4())
        now = self._now()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO posts (
                    id, account_id, brand_name, channel, title, slug, excerpt,
                    body_markdown, body_html, cta_text, cta_url, target_audience,
                    campaign_id, post_type, status, seo_title, seo_description,
                    focus_keyword, og_image_url, featured_image_url, scheduled_for,
                    published_at, created_by, approved_by, created_at, updated_at
                ) VALUES (
                    :id, :account_id, :brand_name, :channel, :title, :slug, :excerpt,
                    :body_markdown, :body_html, :cta_text, :cta_url, :target_audience,
                    :campaign_id, :post_type, :status, :seo_title, :seo_description,
                    :focus_keyword, :og_image_url, :featured_image_url, :scheduled_for,
                    :published_at, :created_by, :approved_by, :created_at, :updated_at
                )
                """,
                {
                    "id": post_id,
                    "account_id": data.get("account_id"),
                    "brand_name": data.get("brand_name", "Raw Sushi Bar"),
                    "channel": data.get("channel", "rawwebsite"),
                    "title": data.get("title"),
                    "slug": data.get("slug"),
                    "excerpt": data.get("excerpt"),
                    "body_markdown": data.get("body_markdown"),
                    "body_html": data.get("body_html"),
                    "cta_text": data.get("cta_text"),
                    "cta_url": data.get("cta_url"),
                    "target_audience": data.get("target_audience"),
                    "campaign_id": data.get("campaign_id"),
                    "post_type": data.get("post_type"),
                    "status": data.get("status", "draft"),
                    "seo_title": data.get("seo_title"),
                    "seo_description": data.get("seo_description"),
                    "focus_keyword": data.get("focus_keyword"),
                    "og_image_url": data.get("og_image_url"),
                    "featured_image_url": data.get("featured_image_url"),
                    "scheduled_for": data.get("scheduled_for"),
                    "published_at": data.get("published_at"),
                    "created_by": data.get("created_by", "ai_agent"),
                    "approved_by": data.get("approved_by"),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            conn.commit()
            return self.get_post(post_id) or {"id": post_id}
        finally:
            conn.close()

    def update_post_status(
        self, post_id: str, status: str, extra: dict | None = None
    ) -> None:
        """Update post status and any extra fields (e.g. approved_by, published_at)."""
        now = self._now()
        fields = {"status": status, "updated_at": now, "id": post_id}
        if extra:
            fields.update(extra)

        set_clauses = ", ".join(
            f"{k} = :{k}" for k in fields if k != "id"
        )
        conn = self._conn()
        try:
            conn.execute(
                f"UPDATE posts SET {set_clauses} WHERE id = :id", fields
            )
            conn.commit()
        finally:
            conn.close()

    def get_post(self, post_id: str) -> dict | None:
        """Return post + latest version as a single dict."""
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT p.*,
                       v.id          AS version_id,
                       v.version_no,
                       v.agent_score,
                       v.review_status AS version_review_status,
                       v.review_notes  AS version_review_notes,
                       v.body_markdown AS version_body_markdown,
                       v.body_html     AS version_body_html,
                       v.featured_image_prompt,
                       v.model_name,
                       v.model_provider
                FROM posts p
                LEFT JOIN post_versions v ON v.post_id = p.id
                    AND v.version_no = (
                        SELECT MAX(version_no) FROM post_versions WHERE post_id = p.id
                    )
                WHERE p.id = ?
                """,
                (post_id,),
            ).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def get_post_detail(self, post_id: str) -> dict | None:
        """Return post + all versions + all review actions."""
        conn = self._conn()
        try:
            post_row = conn.execute(
                "SELECT * FROM posts WHERE id = ?", (post_id,)
            ).fetchone()
            if not post_row:
                return None
            post = self._row_to_dict(post_row)

            versions = [
                self._row_to_dict(r)
                for r in conn.execute(
                    "SELECT * FROM post_versions WHERE post_id = ? ORDER BY version_no ASC",
                    (post_id,),
                ).fetchall()
            ]

            actions = [
                self._row_to_dict(r)
                for r in conn.execute(
                    """
                    SELECT * FROM post_review_actions
                    WHERE post_id = ?
                    ORDER BY created_at ASC
                    """,
                    (post_id,),
                ).fetchall()
            ]

            post["versions"] = versions
            post["review_timeline"] = actions
            return post
        finally:
            conn.close()

    def list_review_queue(
        self,
        status: str | None = None,
        channel: str | None = None,
        brand: str | None = None,
        post_type: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """List posts joined with their latest version for the review queue."""
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("p.status = ?")
            params.append(status)
        if channel:
            conditions.append("p.channel = ?")
            params.append(channel)
        if brand:
            conditions.append("p.brand_name LIKE ?")
            params.append(f"%{brand}%")
        if post_type:
            conditions.append("p.post_type = ?")
            params.append(post_type)
        if keyword:
            conditions.append("(p.title LIKE ? OR p.excerpt LIKE ? OR p.focus_keyword LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])

        conn = self._conn()
        try:
            rows = conn.execute(
                f"""
                SELECT
                    p.id, p.brand_name, p.channel, p.title, p.slug, p.excerpt,
                    p.post_type, p.status, p.focus_keyword, p.cta_url,
                    p.created_by, p.approved_by, p.created_at, p.updated_at,
                    p.scheduled_for, p.published_at,
                    v.id          AS version_id,
                    v.version_no,
                    v.agent_score,
                    v.review_status,
                    v.model_name
                FROM posts p
                LEFT JOIN post_versions v ON v.post_id = p.id
                    AND v.version_no = (
                        SELECT MAX(version_no) FROM post_versions WHERE post_id = p.id
                    )
                {where}
                ORDER BY p.updated_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def count_pending(self) -> int:
        """Count posts awaiting review (status='review_pending')."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM posts WHERE status = 'review_pending'"
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    # ── post_versions ──────────────────────────────────────────────────────────

    def get_next_version_no(self, post_id: str) -> int:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 AS next FROM post_versions WHERE post_id = ?",
                (post_id,),
            ).fetchone()
            return row["next"] if row else 1
        finally:
            conn.close()

    def create_version(self, data: dict) -> dict:
        """Insert a new post_versions row. Returns the created row as dict."""
        version_id = data.get("id") or str(uuid4())
        post_id = data["post_id"]
        version_no = data.get("version_no") or self.get_next_version_no(post_id)
        now = self._now()

        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO post_versions (
                    id, post_id, version_no, generation_prompt, model_provider, model_name,
                    title, excerpt, body_markdown, body_html, cta_text, cta_url,
                    seo_title, seo_description, focus_keyword, featured_image_prompt,
                    featured_image_url, agent_score, review_status, review_notes, created_at
                ) VALUES (
                    :id, :post_id, :version_no, :generation_prompt, :model_provider, :model_name,
                    :title, :excerpt, :body_markdown, :body_html, :cta_text, :cta_url,
                    :seo_title, :seo_description, :focus_keyword, :featured_image_prompt,
                    :featured_image_url, :agent_score, :review_status, :review_notes, :created_at
                )
                """,
                {
                    "id": version_id,
                    "post_id": post_id,
                    "version_no": version_no,
                    "generation_prompt": data.get("generation_prompt"),
                    "model_provider": data.get("model_provider", "anthropic"),
                    "model_name": data.get("model_name"),
                    "title": data.get("title"),
                    "excerpt": data.get("excerpt"),
                    "body_markdown": data.get("body_markdown"),
                    "body_html": data.get("body_html"),
                    "cta_text": data.get("cta_text"),
                    "cta_url": data.get("cta_url"),
                    "seo_title": data.get("seo_title"),
                    "seo_description": data.get("seo_description"),
                    "focus_keyword": data.get("focus_keyword"),
                    "featured_image_prompt": data.get("featured_image_prompt"),
                    "featured_image_url": data.get("featured_image_url"),
                    "agent_score": data.get("agent_score", 0.0),
                    "review_status": data.get("review_status", "pending"),
                    "review_notes": data.get("review_notes"),
                    "created_at": now,
                },
            )
            conn.commit()

            row = conn.execute(
                "SELECT * FROM post_versions WHERE id = ?", (version_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else {"id": version_id}
        finally:
            conn.close()

    def update_version_review_status(
        self, version_id: str, review_status: str, notes: str | None = None
    ) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE post_versions SET review_status = ?, review_notes = ? WHERE id = ?",
                (review_status, notes, version_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── post_review_actions ────────────────────────────────────────────────────

    def add_review_action(self, data: dict) -> dict:
        """Insert a post_review_actions row. Returns the created row as dict."""
        action_id = data.get("id") or str(uuid4())
        now = self._now()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO post_review_actions (
                    id, post_id, post_version_id, actor, actor_type, action_type,
                    from_status, to_status, comment, payload_json, created_at
                ) VALUES (
                    :id, :post_id, :post_version_id, :actor, :actor_type, :action_type,
                    :from_status, :to_status, :comment, :payload_json, :created_at
                )
                """,
                {
                    "id": action_id,
                    "post_id": data["post_id"],
                    "post_version_id": data.get("post_version_id"),
                    "actor": data.get("actor", "system"),
                    "actor_type": data.get("actor_type", "system"),
                    "action_type": data["action_type"],
                    "from_status": data.get("from_status"),
                    "to_status": data.get("to_status"),
                    "comment": data.get("comment"),
                    "payload_json": json.dumps(data.get("payload", {})),
                    "created_at": now,
                },
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM post_review_actions WHERE id = ?", (action_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else {"id": action_id}
        finally:
            conn.close()

    def get_post_logs(self, post_id: str) -> list[dict]:
        """Return all review actions for a post, newest first."""
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT * FROM post_review_actions
                WHERE post_id = ?
                ORDER BY created_at ASC
                """,
                (post_id,),
            ).fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # ── audit_log integration ──────────────────────────────────────────────────

    def add_audit_entry(
        self,
        actor: str,
        action_type: str,
        entity_id: str,
        details: dict | None = None,
        from_state: dict | None = None,
        to_state: dict | None = None,
    ) -> None:
        """Write a row to the existing audit_log table with entity_type='post'."""
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO audit_log (
                    id, timestamp, actor, action_type, entity_type, entity_id,
                    details_json, previous_state_json, new_state_json
                ) VALUES (?, datetime('now'), ?, ?, 'post', ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    actor,
                    action_type,
                    entity_id,
                    json.dumps(details or {}),
                    json.dumps(from_state) if from_state else None,
                    json.dumps(to_state) if to_state else None,
                ),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("audit_log write failed (non-fatal): %s", exc)
        finally:
            conn.close()
