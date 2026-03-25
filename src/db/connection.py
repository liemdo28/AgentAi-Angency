"""SQLite connection management with WAL mode and schema initialization."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

# Path to the SQLite database file (gitignored)
DB_PATH = Path(__file__).parent.parent.parent / "data" / "agency.db"


def _get_connection() -> sqlite3.Connection:
    """Create a new SQLite connection with safe settings."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# Thread-local connection storage
_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Get a thread-local SQLite connection. Creates one if not yet created."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _get_connection()
    return _local.conn


def close_db() -> None:
    """Close the thread-local connection."""
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None


def dict_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a sqlite3.Row to a plain dict."""
    return dict(zip(row.keys(), row))


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert an iterable of sqlite3.Row to a list of dicts."""
    return [dict_from_row(r) for r in rows]


def init_db() -> None:
    """Initialize the database schema. Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS)."""
    from src.db.schema import SQL_SCHEMA

    conn = get_db()
    cursor = conn.cursor()

    # Execute schema statements
    for statement in SQL_SCHEMA.split(";"):
        statement = statement.strip()
        if statement:
            cursor.executescript(statement)

    conn.commit()
    cursor.close()
