"""
Seed posts for Raw Sushi Bar Stockton.

These are pre-approved, ready-to-use posts that can be loaded via
SocialService.seed_posts() to bootstrap a new store's content queue.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .models import (
    ContentType,
    Platform,
    PostGoal,
    SocialPost,
    SocialPostStatus,
    StoreProfile,
)

# ── Raw data ───────────────────────────────────────────────────────────────────

SEED_POSTS_STOCKTON: list[dict] = [
    {
        "store_id": "raw_stockton",
        "content_type": "freshness_push",
        "goal": "drive_order",
        "headline": "Fresh sushi hits different today 🍣",
        "body": (
            "Craving something fresh and satisfying? Raw Sushi Bar Stockton serves "
            "fresh sushi, signature rolls, and Japanese favorites made to order."
        ),
        "cta": "Order now 👉 https://www.rawsushibar.com/order/stockton/",
        "hashtags": [
            "#StocktonFood",
            "#SushiLovers",
            "#FreshSushi",
            "#JapaneseFood",
            "#SushiNearMe",
        ],
        "seo_terms": ["sushi Stockton", "fresh sushi near me"],
        "scheduled_at": None,
        "status": "approved",
    },
    {
        "store_id": "raw_stockton",
        "content_type": "local_seo_post",
        "goal": "local_seo",
        "headline": "Looking for sushi in Stockton tonight?",
        "body": (
            "If you're searching for fresh sushi in Stockton, Raw Sushi Bar is ready "
            "for dinner. Great flavors, easy ordering, and local favorites all in one place."
        ),
        "cta": "View menu 👉 https://www.rawsushibar.com/menu/stockton/",
        "hashtags": ["#BestSushiStockton", "#FoodieLife", "#SushiTime"],
        "seo_terms": ["sushi Stockton", "Japanese restaurant Stockton"],
        "scheduled_at": None,
        "status": "approved",
    },
    {
        "store_id": "raw_stockton",
        "content_type": "order_cta_post",
        "goal": "drive_order",
        "headline": "Lunch plans = solved 🍱",
        "body": (
            "Quick, fresh, and full of flavor. Stop by Raw Sushi Bar Stockton for "
            "a lunch that feels light but satisfying."
        ),
        "cta": "Visit us today 👉 https://www.rawsushibar.com/stockton/",
        "hashtags": ["#DinnerIdeas", "#StocktonEats", "#SushiNight"],
        "seo_terms": ["sushi Stockton", "fresh sushi near me"],
        "scheduled_at": None,
        "status": "approved",
    },
    {
        "store_id": "raw_stockton",
        "content_type": "weekend_vibe_post",
        "goal": "drive_group_dining",
        "headline": "Weekend sushi mood starts now 🔥",
        "body": (
            "Good food, fresh rolls, and the kind of meal you'll want to share. "
            "Raw Sushi Bar Stockton is ready for your weekend plans."
        ),
        "cta": "Book or visit today 👉 https://www.rawsushibar.com/stockton/",
        "hashtags": ["#WeekendVibes", "#FoodWithFriends", "#SushiBar"],
        "seo_terms": ["sushi Stockton", "Japanese restaurant Stockton"],
        "scheduled_at": None,
        "status": "approved",
    },
    {
        "store_id": "raw_stockton",
        "content_type": "social_proof_post",
        "goal": "build_trust",
        "headline": "One bite and you'll get it 😍",
        "body": (
            "Fresh ingredients, bold flavors, and a local sushi experience people "
            "keep coming back for in Stockton."
        ),
        "cta": "Check the menu 👉 https://www.rawsushibar.com/menu/stockton/",
        "hashtags": ["#FoodCravings", "#SushiAddict", "#StocktonFoodie"],
        "seo_terms": ["best sushi in Stockton", "fresh sushi Stockton"],
        "scheduled_at": None,
        "status": "approved",
    },
]


# ── Builder ────────────────────────────────────────────────────────────────────

_CONTENT_TYPE_MAP: dict[str, ContentType] = {ct.value: ct for ct in ContentType}
_GOAL_MAP: dict[str, PostGoal] = {g.value: g for g in PostGoal}
_STATUS_MAP: dict[str, SocialPostStatus] = {s.value: s for s in SocialPostStatus}


def build_seed_posts(store: StoreProfile | None = None) -> list[SocialPost]:
    """Convert the raw SEED_POSTS_STOCKTON dicts into SocialPost objects.

    Args:
        store: The StoreProfile to associate with the seed posts.

    Returns:
        A list of SocialPost objects with status=APPROVED.
    """
    posts: list[SocialPost] = []
    if store is None:
        from .store_profiles import get_store
        store = get_store("raw_stockton")
    raw_list = SEED_POSTS_STOCKTON if store.store_id == "raw_stockton" else []

    for raw in raw_list:
        content_type_str = raw["content_type"]
        # weekend_vibe_post and social_proof_post come in without the canonical
        # enum value prefix — normalise them
        if not content_type_str.endswith("_post") and content_type_str in (
            "freshness_push",
            "local_seo_post",
            "order_cta_post",
            "menu_highlight",
            "seasonal",
            "review_based",
            "event",
        ):
            content_type_val = content_type_str
        else:
            content_type_val = content_type_str

        content_type = _CONTENT_TYPE_MAP.get(content_type_val, ContentType.FRESHNESS_PUSH)
        goal = _GOAL_MAP.get(raw["goal"], PostGoal.DRIVE_VISIT)
        status = _STATUS_MAP.get(raw["status"], SocialPostStatus.APPROVED)

        posts.append(
            SocialPost(
                id=str(uuid.uuid4()),
                store_id=store.store_id,
                platform=store.platforms[0] if store.platforms else Platform.FACEBOOK,
                content_type=content_type,
                goal=goal,
                status=status,
                headline=raw["headline"],
                body=raw["body"],
                cta=raw["cta"],
                hashtags=raw["hashtags"],
                seo_terms=raw["seo_terms"],
                scheduled_at=raw.get("scheduled_at"),
                created_at=datetime.now(timezone.utc),
            )
        )

    return posts
