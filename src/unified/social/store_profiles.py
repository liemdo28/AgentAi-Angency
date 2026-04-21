"""
Hard-coded store profiles for Raw Sushi Bar locations.

Add new locations here; set is_active=False to exclude from pipelines.
"""

from __future__ import annotations

import logging

from .models import ApprovalMode, Platform, StoreProfile, ToneProfile

logger = logging.getLogger("social.store_profiles")

# ── Profiles ───────────────────────────────────────────────────────────────────

STORE_PROFILES: dict[str, StoreProfile] = {
    "raw_stockton": StoreProfile(
        store_id="raw_stockton",
        store_name="Raw Sushi Bar Stockton",
        city="Stockton",
        state="CA",
        country="US",
        timezone="America/Los_Angeles",
        address="10742 Trinity Parkway Suite D, Stockton, CA 95219",
        phone="(209) 954-9729",
        order_url="https://order.toasttab.com/online/raw-sushi-bistro-10742-trinity-pkwy-ste-d",
        menu_url="https://www.rawsushibar.com/menu/stockton/",
        location_url="https://www.rawsushibar.com/stockton/",
        primary_keywords=[
            "sushi Stockton",
            "best sushi in Stockton",
            "Japanese restaurant Stockton",
        ],
        secondary_keywords=[
            "fresh sushi near me",
            "sushi rolls Stockton",
            "sashimi Stockton",
            "Japanese food Stockton",
        ],
        tone_profile=ToneProfile(
            style="friendly, modern, local, premium-casual",
            reading_level="simple",
            emoji_level="light",
        ),
        posting_hours=["11:30", "18:00"],
        platforms=[Platform.FACEBOOK, Platform.INSTAGRAM],
        target_actions=["visit", "order", "reserve"],
        approval_mode=ApprovalMode.APPROVAL_REQUIRED,
        is_active=True,
    ),
    "raw_modesto": StoreProfile(
        store_id="raw_modesto",
        store_name="Raw Sushi Bar Modesto",
        city="Modesto",
        state="CA",
        country="US",
        timezone="America/Los_Angeles",
        address="1200 I Street, Modesto, CA 95354",
        phone="(209) 526-8700",
        order_url=None,
        menu_url="https://www.rawsushibar.com/menu/modesto/",
        location_url="https://www.rawsushibar.com/modesto/",
        primary_keywords=[
            "sushi Modesto",
            "best sushi in Modesto",
            "Japanese restaurant Modesto",
        ],
        secondary_keywords=[
            "fresh sushi near me",
            "sushi Modesto CA",
            "Japanese food Modesto",
        ],
        tone_profile=ToneProfile(
            style="friendly, local, warm, casual",
            reading_level="simple",
            emoji_level="light",
        ),
        posting_hours=["11:30", "17:30"],
        platforms=[Platform.FACEBOOK, Platform.INSTAGRAM],
        target_actions=["visit", "reserve"],
        approval_mode=ApprovalMode.APPROVAL_REQUIRED,
        is_active=True,
    ),
}


# ── Accessors ──────────────────────────────────────────────────────────────────

def get_store(store_id: str) -> StoreProfile:
    """Return a StoreProfile by store_id.

    Raises:
        KeyError: if the store_id is not registered.
    """
    if store_id not in STORE_PROFILES:
        raise KeyError(f"Unknown store_id: {store_id!r}. Available: {list(STORE_PROFILES)}")
    return STORE_PROFILES[store_id]


def get_active_stores() -> list[StoreProfile]:
    """Return all store profiles where is_active is True."""
    return [s for s in STORE_PROFILES.values() if s.is_active]
