"""Account repository — SQLite CRUD for accounts."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.db.connection import get_db

logger = logging.getLogger(__name__)


class AccountRepository:
    TABLE = "accounts"

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        db = get_db()
        data["metadata_json"] = json.dumps(data.get("metadata_json", {}))
        cols = [k for k, v in data.items() if v is not None]
        placeholders = ", ".join(f":{c}" for c in cols)
        col_names = ", ".join(cols)
        db.execute(
            f"INSERT INTO {self.TABLE} ({col_names}) VALUES ({placeholders})",
            data,
        )
        db.commit()
        logger.info("AccountRepository: created account %s", data.get("id"))
        return data

    def get(self, account_id: str) -> Optional[dict[str, Any]]:
        db = get_db()
        row = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (account_id,)
        ).fetchone()
        return dict(row) if row else None

    def update(self, account_id: str, updates: dict[str, Any]) -> None:
        db = get_db()
        updates["updated_at"] = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        setters = ", ".join(f"{k} = :{k}" for k in updates)
        db.execute(
            f"UPDATE {self.TABLE} SET {setters} WHERE id = :id",
            {"id": account_id, **updates},
        )
        db.commit()

    def list_all(self) -> list[dict[str, Any]]:
        db = get_db()
        rows = db.execute(f"SELECT * FROM {self.TABLE} ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def add_memory(
        self,
        account_id: str,
        memory_type: str,
        content: str,
        relevance_score: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        import uuid
        db = get_db()
        db.execute(
            """INSERT INTO account_memory
               (id, account_id, memory_type, content, relevance_score, metadata_json)
               VALUES (:id, :account_id, :memory_type, :content, :relevance_score, :metadata_json)""",
            {
                "id": str(uuid.uuid4()),
                "account_id": account_id,
                "memory_type": memory_type,
                "content": content,
                "relevance_score": relevance_score,
                "metadata_json": json.dumps(metadata or {}),
            },
        )
        db.commit()

    def get_memory(
        self,
        account_id: str,
        memory_type: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        db = get_db()
        if memory_type:
            rows = db.execute(
                """SELECT * FROM account_memory
                   WHERE account_id = ? AND memory_type = ?
                   ORDER BY relevance_score DESC, created_at DESC LIMIT ?""",
                (account_id, memory_type, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT * FROM account_memory
                   WHERE account_id = ?
                   ORDER BY relevance_score DESC, created_at DESC LIMIT ?""",
                (account_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


class CampaignRepository:
    """SQLite CRUD for campaigns + campaign_memory table."""

    TABLE = "campaigns"

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        db = get_db()
        data["metadata_json"] = json.dumps(data.get("metadata_json", {}))
        cols = [k for k, v in data.items() if v is not None]
        placeholders = ", ".join(f":{c}" for c in cols)
        col_names = ", ".join(cols)
        db.execute(
            f"INSERT INTO {self.TABLE} ({col_names}) VALUES ({placeholders})",
            data,
        )
        db.commit()
        logger.info("CampaignRepository: created campaign %s", data.get("id"))
        return data

    def get(self, campaign_id: str) -> Optional[dict[str, Any]]:
        db = get_db()
        row = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (campaign_id,)
        ).fetchone()
        return dict(row) if row else None

    def update(self, campaign_id: str, updates: dict[str, Any]) -> None:
        db = get_db()
        updates["updated_at"] = __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        setters = ", ".join(f"{k} = :{k}" for k in updates)
        db.execute(
            f"UPDATE {self.TABLE} SET {setters} WHERE id = :id",
            {"id": campaign_id, **updates},
        )
        db.commit()

    def list_all(self) -> list[dict[str, Any]]:
        db = get_db()
        rows = db.execute(f"SELECT * FROM {self.TABLE} ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def list_by_account(self, account_id: str) -> list[dict[str, Any]]:
        db = get_db()
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE account_id = ? ORDER BY created_at DESC",
            (account_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_event(
        self,
        campaign_id: str,
        event_type: str,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        import uuid
        db = get_db()
        db.execute(
            """INSERT INTO campaign_memory
               (id, campaign_id, event_type, description, metadata_json)
               VALUES (:id, :cid, :type, :desc, :meta)""",
            {
                "id": str(uuid.uuid4()),
                "cid": campaign_id,
                "type": event_type,
                "desc": description,
                "meta": json.dumps(metadata or {}),
            },
        )
        db.commit()

    def get_events(
        self,
        campaign_id: str,
        event_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        db = get_db()
        if event_type:
            rows = db.execute(
                """SELECT * FROM campaign_memory
                   WHERE campaign_id = ? AND event_type = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (campaign_id, event_type, limit),
            ).fetchall()
        else:
            rows = db.execute(
                """SELECT * FROM campaign_memory
                   WHERE campaign_id = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (campaign_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
