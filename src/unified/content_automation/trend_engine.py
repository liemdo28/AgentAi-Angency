"""
Trend Engine — placeholder for Phase 2.

Phase 1: returns empty results. The planner falls back to brand-theme pools only.

Phase 2 will implement:
  - US / California / local (Stockton/Modesto) headline fetching
  - Seasonal calendar integration
  - Food trend APIs
  - Relevance + risk scoring
  - Topic transformation into restaurant-relevant angles
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from .models import RiskLevel, TrendSignal

logger = logging.getLogger("content_automation.trend_engine")


class TrendEngine:
    """
    Collects and scores trend signals for content planning.

    Phase 1: always returns an empty list. Slots are planned from
    brand-theme pools only (configured in core/content/store_data.py).

    Phase 2: implement _fetch_signals() to pull from live sources.
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand

    def get_trends(
        self,
        geography: str = "local",
        category: str = "food",
        limit: int = 5,
    ) -> list[TrendSignal]:
        """
        Return scored trend signals for the given geography + category.

        Phase 1: returns empty list. Phase 2 returns filtered TrendSignal objects.
        """
        logger.debug(
            "[Phase1] TrendEngine.get_trends called — not yet implemented. "
            "Returning empty list. geography=%r category=%r",
            geography, category,
        )
        return []

    def score_signal(self, signal: TrendSignal) -> TrendSignal:
        """
        Score a raw signal: relevance, risk, publishability.

        Phase 1: returns the signal unchanged with LOW risk.

        Phase 2: implement actual scoring:
          - relevance_score: how directly it connects to dining intent
          - risk_level: BLOCK for tragedies, controversial topics, etc.
          - publishable: True unless risk_level == BLOCK
        """
        signal.relevance_score = 0.0
        signal.risk_level = RiskLevel.LOW
        signal.publishable = True
        return signal

    def refresh_trends(self) -> dict:
        """
        Trigger a manual refresh of cached trend data.

        Phase 1: no-op. Phase 2: pull fresh from APIs and update cache.
        """
        logger.info("[Phase1] TrendEngine.refresh_trends — not yet implemented.")
        return {
            "status": "phase1_not_implemented",
            "message": "Trend refresh is a Phase 2 feature.",
            "fetched_count": 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Constants (Phase 2 reference — used by future implementation)
# ─────────────────────────────────────────────────────────────────────────────

# Blocked topics — never used regardless of relevance score
BLOCKED_KEYWORDS = [
    "tragedy", "death", "murder", "assault", "accident",
    "scandal", "lawsuit", "fraud", "abuse",
]

# Minimum relevance score (0-1) to be considered for content
MIN_RELEVANCE_SCORE = 0.5

# Geographic priority order
GEO_PRIORITY = ["local", "regional", "california", "us"]


def _transform_to_restaurant_topic(trend: TrendSignal) -> str:
    """
    Transform a scored trend into a restaurant-relevant topic title.

    Phase 2 implementation reference:
      - "SF Giants win World Series"  → "Game Night Dining: Where to Watch the Giants Near Stockton"
      - "California drought advisory" → "Beat the Heat: Cool Down with Fresh Sushi This Summer"
      - "Modesto taco festival"       → "Sushi Night After the Festival? Try Raw Sushi Bar"

    The key rule: connect the trend to a natural dining need, not the trend itself.
    """
    return trend.topic
