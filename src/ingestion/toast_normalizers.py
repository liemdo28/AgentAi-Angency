"""
toast_normalizers.py — Normalize Toast data: store names, channels, item names.

Each normalizer loads config from DB (store_aliases, channel_aliases, item_aliases)
and provides a normalize() method that maps raw Toast values to canonical ones.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)


# ── Store Normalizer ─────────────────────────────────────────────────────────

class StoreNormalizer:
    """
    Map raw Toast location names to internal store_id.

    Uses store_aliases table for exact match (lowered, trimmed).
    Falls back to substring matching if no exact match found.
    """

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._cache: dict[str, str] = {}
        self._alias_map: dict[str, tuple[str, str]] = {}  # alias -> (store_id, store_name)
        self._load()

    def _load(self) -> None:
        rows = self._db.execute(
            "SELECT alias, store_id, store_name FROM store_aliases"
        ).fetchall()
        for row in rows:
            alias = row["alias"].strip().lower()
            self._alias_map[alias] = (row["store_id"], row["store_name"] or "")
        logger.info("StoreNormalizer loaded %d aliases", len(self._alias_map))

    def normalize(self, raw_location: str | None) -> str | None:
        """Return internal store_id for a raw location string, or None if unmatched."""
        if not raw_location:
            return None

        key = raw_location.strip().lower()
        if key in self._cache:
            return self._cache[key]

        # Exact match
        if key in self._alias_map:
            store_id = self._alias_map[key][0]
            self._cache[key] = store_id
            return store_id

        # Substring match — find the alias that is contained in the raw location
        for alias, (store_id, _) in self._alias_map.items():
            if alias in key or key in alias:
                self._cache[key] = store_id
                return store_id

        # No match
        logger.warning("Unknown store location: '%s'", raw_location)
        self._cache[key] = None  # type: ignore[assignment]
        return None

    def add_alias(self, alias: str, store_id: str, store_name: str = "", brand: str = "") -> None:
        """Add a new store alias to DB and refresh cache."""
        norm_alias = alias.strip().lower()
        self._db.execute(
            "INSERT OR IGNORE INTO store_aliases (alias, store_id, store_name, brand) VALUES (?, ?, ?, ?)",
            (norm_alias, store_id, store_name, brand),
        )
        self._db.commit()
        self._alias_map[norm_alias] = (store_id, store_name)
        self._cache.pop(norm_alias, None)


# ── Channel Normalizer ───────────────────────────────────────────────────────

class ChannelNormalizer:
    """
    Map raw Toast dining options / sources to canonical channels:
      dine_in, pickup, delivery, catering, bar, other
    """

    CANONICAL_CHANNELS = {"dine_in", "pickup", "delivery", "catering", "bar", "other"}

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._alias_map: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        rows = self._db.execute(
            "SELECT alias, channel FROM channel_aliases"
        ).fetchall()
        for row in rows:
            self._alias_map[row["alias"].strip().lower()] = row["channel"]
        logger.info("ChannelNormalizer loaded %d aliases", len(self._alias_map))

    def normalize(self, raw_value: str | None) -> str:
        """Return canonical channel name. Defaults to 'other' if unmatched."""
        if not raw_value:
            return "other"

        key = raw_value.strip().lower()

        # Exact match
        if key in self._alias_map:
            return self._alias_map[key]

        # Substring match
        for alias, channel in self._alias_map.items():
            if alias in key or key in alias:
                return channel

        # Keyword fallback
        if any(w in key for w in ("dine", "eat in", "for here")):
            return "dine_in"
        if any(w in key for w in ("take", "pickup", "pick up", "online")):
            return "pickup"
        if any(w in key for w in ("deliver", "uber", "doordash", "grubhub", "postmate", "caviar")):
            return "delivery"
        if "cater" in key:
            return "catering"
        if "bar" in key:
            return "bar"

        logger.debug("Unknown channel: '%s', defaulting to 'other'", raw_value)
        return "other"

    def add_alias(self, alias: str, channel: str) -> None:
        """Add a new channel alias to DB and refresh cache."""
        norm_alias = alias.strip().lower()
        if channel not in self.CANONICAL_CHANNELS:
            logger.warning("Non-standard channel '%s' for alias '%s'", channel, alias)
        self._db.execute(
            "INSERT OR IGNORE INTO channel_aliases (alias, channel) VALUES (?, ?)",
            (norm_alias, channel),
        )
        self._db.commit()
        self._alias_map[norm_alias] = channel


# ── Item Normalizer ──────────────────────────────────────────────────────────

class ItemNormalizer:
    """
    Normalize item names from Toast:
      - Trim whitespace
      - Remove duplicate spacing
      - Apply alias resolution from item_aliases table
      - Always keep raw_item_name alongside normalized item_name
    """

    def __init__(self, db: sqlite3.Connection):
        self._db = db
        self._alias_map: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        rows = self._db.execute(
            "SELECT alias, canonical_name FROM item_aliases"
        ).fetchall()
        for row in rows:
            self._alias_map[row["alias"].strip().lower()] = row["canonical_name"]
        logger.info("ItemNormalizer loaded %d aliases", len(self._alias_map))

    def normalize(self, raw_name: str | None) -> str:
        """Return normalized item name. Preserves original if no alias found."""
        if not raw_name:
            return ""

        # Basic cleanup
        cleaned = raw_name.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)  # collapse multiple spaces

        key = cleaned.lower()

        # Exact alias match
        if key in self._alias_map:
            return self._alias_map[key]

        # Title-case the cleaned name as default normalization
        return cleaned

    def add_alias(self, alias: str, canonical_name: str, category: str = "") -> None:
        """Add a new item alias to DB and refresh cache."""
        norm_alias = alias.strip().lower()
        self._db.execute(
            "INSERT OR IGNORE INTO item_aliases (alias, canonical_name, category) VALUES (?, ?, ?)",
            (norm_alias, canonical_name, category),
        )
        self._db.commit()
        self._alias_map[norm_alias] = canonical_name


# ── Row Normalizer (combines all three) ──────────────────────────────────────

class ToastRowNormalizer:
    """
    Convenience class that combines store, channel, and item normalization
    for processing full rows.
    """

    def __init__(self, db: sqlite3.Connection):
        self.store = StoreNormalizer(db)
        self.channel = ChannelNormalizer(db)
        self.item = ItemNormalizer(db)

    def normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize a single row in-place:
          - Add store_id from location
          - Add channel from dining_option/source
          - Normalize item_name (keep raw_item_name)
        """
        # Store
        location = row.get("location")
        row["store_id"] = self.store.normalize(location)
        row["location_raw"] = location

        # Channel
        dining = row.get("dining_option") or row.get("source")
        if dining:
            row["channel"] = self.channel.normalize(dining)

        # Item
        item = row.get("item_name")
        if item:
            row["raw_item_name"] = item
            row["item_name"] = self.item.normalize(item)

        # Modifier
        mod = row.get("modifier_name")
        if mod:
            row["modifier_name"] = self.item.normalize(mod)

        # Parent item
        parent = row.get("parent_item")
        if parent:
            row["parent_item"] = self.item.normalize(parent)

        return row
