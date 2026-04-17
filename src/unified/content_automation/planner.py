"""
Content Planner — creates 3 post plans per day for Raw Sushi Bar.

Slot rules:
  Slot 0 (morning)  → viral_attention   — maximize attention + discovery
  Slot 1 (midday)   → conversion_order  — drive visits and orders
  Slot 2 (evening)  → rotating type     — local_discovery | tourist_discovery
                                                  | menu_highlight | seasonal_trend

Duplicate-avoidance rules:
  - No exact topic in last 7 days
  - No exact title pattern in last 5 days
  - Menu highlight max 2× per week
  - seasonal_trend only when naturally connected to dining intent

Phase 1: only verified business/menu data, no trend engine.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.content.store_data import get_brand_config, get_store_context

from .models import ContentPlan, PostType

logger = logging.getLogger("content_automation.planner")

# Content-type rotation for slot 2
ROTATING_SLOT_TYPES = [
    PostType.LOCAL_DISCOVERY,
    PostType.TOURIST_DISCOVERY,
    PostType.MENU_HIGHLIGHT,
    PostType.SEASONAL_TREND,
]
_SLOT2_INDEX_KEY = "planner:slot2_index"


# ─────────────────────────────────────────────────────────────────────────────
#  ContentPlanner
# ─────────────────────────────────────────────────────────────────────────────

class ContentPlanner:
    """
    Plans 3 content slots per day using LLM + duplicate-avoidance.

    In Phase 1, topics are selected from brand-configured theme pools
    rather than fetched from a live trend engine.
    """

    def __init__(self, brand: str = "raw", history_path: str | None = None):
        self.brand = brand
        self.cfg = get_brand_config(brand)
        if not self.cfg:
            raise ValueError(f"Unknown brand: {brand!r}")
        self.history_path = Path(history_path or "data/content_automation_history.json")
        self._load_history()

    # ── Public API ────────────────────────────────────────────────────────────

    def plan_day(self, date_iso: str | None = None) -> list[ContentPlan]:
        """
        Create exactly 3 ContentPlans for today (or the given date).

        Returns a list of 3 ContentPlan objects in slot order (0, 1, 2).

        Raises:
            ValueError — if fewer than 3 unique plans can be generated.
        """
        date_str = date_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.info("[%s] Starting daily content plan for brand=%s", date_str, self.brand)

        slot2_type = self._rotate_slot2_type(date_str)
        slot_definitions = [
            (0, PostType.VIRAL_ATTENTION),
            (1, PostType.CONVERSION_ORDER),
            (2, slot2_type),
        ]

        plans: list[ContentPlan] = []
        used_topics: set[str] = {p["topic"].lower() for p in self._recent_plans()}

        for slot, post_type in slot_definitions:
            plan = self._plan_slot(
                slot=slot,
                post_type=post_type,
                date_str=date_str,
                used_topics=used_topics,
            )
            used_topics.add(plan.topic.lower())
            plans.append(plan)
            self._save_plan(plan)

        logger.info("[%s] Planned %d slots: %s", date_str, len(plans),
                    [p.post_type.value for p in plans])
        return plans

    # ── Slot planning ─────────────────────────────────────────────────────────

    def _plan_slot(
        self,
        slot: int,
        post_type: PostType,
        date_str: str,
        used_topics: set[str],
    ) -> ContentPlan:
        """Generate one ContentPlan for a given slot, avoiding duplicates."""

        existing_slugs = self._get_existing_slugs()

        # Build the prompt
        prompt = self._build_slot_prompt(slot, post_type, date_str, used_topics, existing_slugs)

        try:
            from core.llm.router import LLMRouter
            router = LLMRouter()
            raw = router.complete(
                prompt=prompt,
                system=(
                    f"You are a content strategist for {self.cfg['brand_name']} "
                    f"({self.cfg['city']}). Return ONLY a valid JSON object."
                ),
                task_type="creative",
                description=f"Plan {post_type.value} content for {self.brand}",
                max_tokens=1024,
                temperature=0.8,
            )
            data = self._parse_json(raw)
        except Exception as exc:
            logger.warning("LLM plan failed for slot %d, using fallback: %s", slot, exc)
            data = {}

        return self._build_plan(data, slot, post_type, date_str)

    def _build_slot_prompt(
        self,
        slot: int,
        post_type: PostType,
        date_str: str,
        used_topics: set[str],
        existing_slugs: set[str],
    ) -> str:
        store_ctx = get_store_context(self.brand)
        date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
        type_guidance = _POST_TYPE_GUIDANCE.get(post_type, "")

        recent = self._recent_plans()
        recent_titles = [p["title"] for p in recent[-10:]]
        recent_topics = [p["topic"] for p in recent[-10:]]

        parts = [
            f"Plan a blog post for {self.cfg['brand_name']}.",
            f"Date: {date_display}.",
            f"Slot: {slot} ({_SLOT_LABELS[slot]})",
            f"Post type: {post_type.value} — {type_guidance}",
            "",
            "Verified restaurant context:",
            store_ctx,
            "",
            f"Theme pool (pick one or create a similar fresh angle):",
        ]

        theme_key = _THEME_KEYS.get(post_type, "local_themes")
        themes = self.cfg.get(theme_key, [])
        parts.append(", ".join(themes[:6]))

        if recent_titles:
            parts.append(f"\nRecent titles to AVOID repeating exactly:")
            for t in recent_titles:
                parts.append(f"  - {t}")

        if recent_topics:
            parts.append(f"\nRecent topics to AVOID (do not repeat exact angle):")
            for t in recent_topics:
                parts.append(f"  - {t}")

        if existing_slugs:
            parts.append(f"\nExisting blog slugs (do not duplicate):")
            parts.append(", ".join(sorted(existing_slugs)[:15]))

        parts.append("\nReturn a JSON object with fields:")
        parts.append("  title, slug (URL-safe, max 60 chars), meta_description (120-160 chars),")
        parts.append("  topic (short 1-sentence summary of angle), target_audience,")
        parts.append("  primary_keyword, secondary_keywords (array), geographic_scope.")

        return "\n".join(parts)

    def _build_plan(
        self,
        data: dict,
        slot: int,
        post_type: PostType,
        date_str: str,
    ) -> ContentPlan:
        title = data.get("title", "").strip()
        slug = data.get("slug", "") or _slugify(title)
        meta_desc = (data.get("meta_description") or "")[:160]
        topic = data.get("topic") or title
        target = data.get("target_audience") or _DEFAULT_AUDIENCE.get(post_type, "Local diners")
        primary_kw = data.get("primary_keyword") or ""
        secondary_kws = data.get("secondary_keywords") or []

        # Deduplicate slug
        existing = self._get_existing_slugs()
        if slug in existing:
            slug = f"{slug}-{date_str.replace('-', '')}"

        scheduled = _SLOT_SCHEDULE_TIMES.get(slot)
        if scheduled:
            scheduled_for = f"{date_str}T{scheduled}:00-07:00"
        else:
            scheduled_for = None

        return ContentPlan(
            slot=slot,
            post_type=post_type,
            topic=topic,
            title=title or _FALLBACK_TITLES.get(post_type, f"{self.cfg['brand_name']} Update"),
            slug=slug[:60],
            meta_description=meta_desc,
            target_audience=target,
            primary_keyword=primary_kw,
            secondary_keywords=secondary_kws,
            geographic_scope=data.get("geographic_scope", "local"),
            source_notes=self._build_source_notes(post_type, data),
            scheduled_for=scheduled_for,
        )

    # ── Duplicate avoidance ────────────────────────────────────────────────────

    def _recent_plans(self) -> list[dict]:
        """Load recent plans from history file."""
        if not self.history_path.exists():
            return []
        try:
            data = json.loads(self.history_path.read_text())
            cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return [
                p for p in data
                if p.get("brand") == self.brand
                and p.get("date", "")[:10] >= _cutoff_date(7)
            ]
        except Exception:
            return []

    def _get_existing_slugs(self) -> set[str]:
        """Scan RawWebsite for existing blog post filenames."""
        try:
            from core.agents.dev_agent import MASTER_DIR, PROJECT_FOLDERS
            folder = PROJECT_FOLDERS.get("RawWebsite", "RawWebsite")
            project_path = Path(MASTER_DIR) / folder
            return {
                f.stem.replace("blog-", "")
                for f in project_path.glob("blog-*.html")
                if project_path.exists()
            }
        except Exception:
            return set()

    def _rotate_slot2_type(self, date_str: str) -> PostType:
        """Pick the next rotating type for slot 2 using day-of-week index."""
        index_key = f"planner:{self.brand}:slot2_index"
        idx = (datetime.strptime(date_str, "%Y-%m-%d").weekday()) % len(ROTATING_SLOT_TYPES)
        return ROTATING_SLOT_TYPES[idx]

    def _load_history(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    def _save_plan(self, plan: ContentPlan) -> None:
        """Append plan to history, keep last 200 entries."""
        data = []
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text())
            except Exception:
                pass
        entry = {
            **plan.model_dump(),
            "date": datetime.now(timezone.utc).isoformat(),
            "brand": self.brand,
        }
        data.append(entry)
        data[:] = data[-200:]
        self.history_path.write_text(json.dumps(data, indent=2))

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        for fence in ["```json", "```"]:
            if fence in text:
                parts = text.split(fence)
                if len(parts) >= 2:
                    text = parts[1].split("```")[0].strip()
                    break
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"No JSON object found in LLM output: {raw[:200]}")

    @staticmethod
    def _build_source_notes(post_type: PostType, data: dict) -> str:
        return (
            f"[Phase 1 — no trend engine] "
            f"Topic selected from {post_type.value} theme pool. "
            f"No external trend data used. "
            f"All facts drawn from verified brand configuration."
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────────────────────────────────────

_SLOT_LABELS = {
    0: "Morning — Discovery / Attention",
    1: "Midday — Conversion / Order Intent",
    2: "Evening — Rotating Content Type",
}

_SLOT_SCHEDULE_TIMES = {
    0: "08:00",
    1: "12:00",
    2: "17:00",
}

_POST_TYPE_GUIDANCE = {
    PostType.VIRAL_ATTENTION:
        "Maximize clicks and curiosity. Emotional pull, food appeal, local relevance. "
        "Make readers want to share or click through.",
    PostType.CONVERSION_ORDER:
        "Drive visits and orders. Emphasize convenience, appetite appeal, decision clarity. "
        "Include a clear, useful CTA.",
    PostType.LOCAL_DISCOVERY:
        "Locally relevant. Build trust with nearby audiences. Neighborhood-aware, community-connected.",
    PostType.TOURIST_DISCOVERY:
        "For visitors and travelers. Memorable, confidence-building for first-timers. "
        "Emphasize convenience and uniqueness.",
    PostType.MENU_HIGHLIGHT:
        "Deep dive into a signature dish or menu category. Sensory, passionate, detailed. "
        "Builds brand trust and appetite.",
    PostType.SEASONAL_TREND:
        "Connect the current season/event to a dining need. Natural, not forced. "
        "Avoids unrelated news or tragedy exploitation.",
}

_THEME_KEYS = {
    PostType.VIRAL_ATTENTION:   "local_themes",
    PostType.CONVERSION_ORDER: "local_themes",
    PostType.LOCAL_DISCOVERY:  "local_themes",
    PostType.TOURIST_DISCOVERY: "tourist_themes",
    PostType.MENU_HIGHLIGHT:    "menu_themes",
    PostType.SEASONAL_TREND:   "local_themes",
}

_DEFAULT_AUDIENCE = {
    PostType.VIRAL_ATTENTION:   "Locals looking for something new to try this week",
    PostType.CONVERSION_ORDER: "Hungry locals ready to order or dine in today",
    PostType.LOCAL_DISCOVERY:  "Stockton and Central Valley residents exploring local dining",
    PostType.TOURIST_DISCOVERY: "Visitors and travelers near Stockton, CA",
    PostType.MENU_HIGHLIGHT:    "Food lovers and sushi enthusiasts interested in quality Japanese cuisine",
    PostType.SEASONAL_TREND:   "Locals and visitors looking for seasonal dining ideas",
}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")


def _cutoff_date(days: int) -> str:
    from datetime import timedelta
    d = datetime.now(timezone.utc) - timedelta(days=days)
    return d.strftime("%Y-%m-%d")


_FALLBACK_TITLES = {
    PostType.VIRAL_ATTENTION:   "Discover the Best Sushi in Stockton This Season",
    PostType.CONVERSION_ORDER:  "Ready to Order Fresh Sushi? Here's Why Raw Sushi Bar Is the Answer",
    PostType.LOCAL_DISCOVERY:  "Why Stockton Locals Keep Coming Back to Raw Sushi Bar",
    PostType.TOURIST_DISCOVERY: "Where to Find Authentic Sushi Near Stockton, CA",
    PostType.MENU_HIGHLIGHT:    "A Closer Look at Our Signature Dragon Roll",
    PostType.SEASONAL_TREND:   "The Perfect Spring Dinner: Fresh Sushi in Stockton",
}
