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
               VALUES (:id, :aid, :type, :content, :score, :meta)""",
            {
                "id": str(uuid.uuid4()),
                "aid": account_id,
                "type": memory_type,
                "content": content,
                "score": relevance_score,
                "meta": json.dumps(metadata or {}),
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
