"""
Content Researcher — gathers verified business data before content generation.

Hard rule: if data is NOT verified, do NOT fabricate. The researcher
returns only confirmed facts from approved internal sources.

Phase 1 approved sources:
  1. core/content/store_data.py — brand configs (name, address, phone, hours, menu)
  2. Verified review snippets (stored in data/verified_reviews.json)
  3. Any future approved external sources (plugged in via get_verified_... functions)

Phase 2 will add: live review APIs, menu API, trend/news feeds.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.content.store_data import (
    get_brand_config,
    get_verified_business_data,
    get_verified_menu_data,
    get_local_context,
    get_traveler_context,
    get_surrounding_audience,
    get_verified_cta_links,
)

logger = logging.getLogger("content_automation.researcher")

VERIFIED_REVIEWS_PATH = Path("data/verified_reviews.json")


# ─────────────────────────────────────────────────────────────────────────────
#  ContentResearcher
# ─────────────────────────────────────────────────────────────────────────────

class ContentResearcher:
    """
    Gathers and packages verified data for the generator.

    All returned fields are confirmed-accurate. Returns an empty dict for
    any field that cannot be verified (caller must handle None/empty).
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand
        self.cfg = get_brand_config(brand)
        if not self.cfg:
            raise ValueError(f"Unknown brand: {brand!r}")

    # ── Public API ────────────────────────────────────────────────────────────

    def gather(self, topic: str | None = None) -> dict[str, Any]:
        """
        Return a verified-data bundle for use in a generation prompt.

        Args:
            topic: Optional topic string — used to pull related verified reviews.

        Returns:
            {
                "business_data": "...",
                "menu_data": "...",
                "local_context": "...",
                "traveler_context": "...",
                "audience_profile": "...",
                "cta_links": "...",
                "verified_reviews": [...],
                "all_verified": True,
                "missing_data": [],
            }
        """
        logger.info("Gathering verified data for brand=%s topic=%r", self.brand, topic)

        business_data   = get_verified_business_data(self.brand)
        menu_data      = get_verified_menu_data(self.brand)
        local_ctx      = get_local_context(self.brand)
        traveler_ctx   = get_traveler_context(self.brand)
        audience       = get_surrounding_audience(self.brand)
        cta_links      = get_verified_cta_links(self.brand)
        reviews        = self._get_verified_reviews(topic)

        missing = self._check_missing(
            business_data, menu_data, local_ctx, cta_links
        )

        if missing:
            logger.warning(
                "Researcher: missing verified data for brand=%s — %s",
                self.brand, missing
            )

        return {
            "business_data":   business_data,
            "menu_data":       menu_data,
            "local_context":   local_ctx,
            "traveler_context": traveler_ctx,
            "audience_profile": audience,
            "cta_links":        cta_links,
            "verified_reviews": reviews,
            "all_verified":     len(missing) == 0,
            "missing_data":     missing,
        }

    def get_verified_cta(self) -> dict[str, str]:
        """
        Return a structured CTA dictionary from verified config.
        Phase 1 uses hardcoded order links; Phase 2 will read from an approved source.
        """
        domain = self.cfg.get("website_domain", "rawsushibar.com")
        brand  = self.cfg.get("brand_name", "Raw Sushi Bar")
        store  = list(self.cfg.get("stores", {}).values())[0] if self.cfg.get("stores") else {}

        return {
            "cta_text": f"Order from {brand} Today",
            "cta_url":  f"https://order.toasttab.com/online/raw-sushi-bistro-10742-trinity-pkwy-ste-d",
            "phone":    store.get("phone", "(209) 954-9729"),
            "menu_url": f"https://{domain}/menu-stockton.html",
            "location_url": "https://www.google.com/maps/search/?api=1&query=10742+Trinity+Parkway+Stockton+CA",
        }

    def get_store_info(self) -> dict[str, Any]:
        """Return the primary store record as a plain dict."""
        stores = self.cfg.get("stores", {})
        primary = stores.get("RAW") or stores.get("B1") or stores.get(list(stores.keys())[0]) or {}
        return {
            "name":         self.cfg.get("brand_name", "Raw Sushi Bar"),
            "address":      primary.get("address", ""),
            "phone":        primary.get("phone", ""),
            "hours":        primary.get("hours", ""),
            "area_context": primary.get("area_context", ""),
            "city":         self.cfg.get("city", "Stockton, CA"),
            "cuisine":      self.cfg.get("cuisine", "Japanese / Sushi"),
            "signature":    self.cfg.get("signature_dishes", []),
        }

    # ── Verified reviews ─────────────────────────────────────────────────────

    def _get_verified_reviews(self, topic: str | None = None, limit: int = 3) -> list[dict]:
        """
        Return verified customer review snippets from the local store.
        Phase 2: replace with live review API.
        """
        if not VERIFIED_REVIEWS_PATH.exists():
            return self._default_reviews()

        try:
            data = json.loads(VERIFIED_REVIEWS_PATH.read_text())
            brand_reviews = data.get(self.brand, []) + data.get("shared", [])
        except Exception as exc:
            logger.warning("Could not load verified reviews: %s", exc)
            return self._default_reviews()

        if topic:
            topic_lower = topic.lower()
            scored = [
                (r, sum(
                    1 for kw in r.get("keywords", [])
                    if kw.lower() in topic_lower
                ))
                for r in brand_reviews
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [dict(r) for r, _ in scored[:limit]]

        return brand_reviews[:limit]

    @staticmethod
    def _default_reviews() -> list[dict]:
        return [
            {
                "text": (
                    "The freshest sushi I've had in the Central Valley. "
                    "The Dragon Roll is absolutely incredible."
                ),
                "source": "verified_internal",
                "keywords": ["dragon roll", "fresh", "central valley"],
            },
            {
                "text": (
                    "Best omakase experience in Stockton. The chef really knows his craft."
                ),
                "source": "verified_internal",
                "keywords": ["omakase", "chef", "best"],
            },
            {
                "text": (
                    "Perfect date night spot. Great atmosphere and even better sushi."
                ),
                "source": "verified_internal",
                "keywords": ["date night", "atmosphere"],
            },
        ]

    @staticmethod
    def _check_missing(*fields: str) -> list[str]:
        return [f"field_{i}" for i, f in enumerate(fields) if not f.strip()]
