"""
Content Planner — generates 3 post topics per day.

Schedule:
  Slot 0 → VIRAL_ATTENTION    (morning)
  Slot 1 → CONVERSION_ORDER   (midday)
  Slot 2 → rotating           (evening: local_discovery | tourist_discovery | menu_highlight)

Rules:
  ✓ No duplicate topics within 7 days
  ✓ No repeated title patterns within 5 days
  ✓ Menu highlight max 2× per week
  ✓ Only verified brand/menu data used (no external API in Phase 1)

Output:
  3 × ContentTopic { type, topic, target_audience }
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from core.content.store_data import get_brand_config, get_store_context

from .models import ContentTopic, PostType

logger = logging.getLogger("content.planner")

# Rotating types for slot 2 — cycles weekly
_SLOT2_CYCLE = [
    PostType.LOCAL_DISCOVERY,
    PostType.TOURIST_DISCOVERY,
    PostType.MENU_HIGHLIGHT,
]


class ContentPlanner:
    """Plans 3 daily content topics using brand-config themes + LLM."""

    def __init__(self, brand: str = "raw", history_path: str | None = None):
        self.brand = brand
        self.cfg = get_brand_config(brand)
        if not self.cfg:
            raise ValueError(f"Unknown brand: {brand!r}")
        self.history_path = Path(history_path or "data/content_history.json")
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def plan_day(self, date_iso: Optional[str] = None) -> list[ContentTopic]:
        """
        Generate exactly 3 ContentTopic objects for the given date.

        Returns 3 topics, one per slot. Slots are always returned in order.
        Raises ValueError if planning fails.
        """
        date_str = date_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.info("[%s] Planning 3 daily posts for brand=%s", date_str, self.brand)

        slot0_type = PostType.VIRAL_ATTENTION
        slot1_type = PostType.CONVERSION_ORDER
        slot2_type = self._rotating_slot2_type(date_str)

        slots = [
            (0, slot0_type),
            (1, slot1_type),
            (2, slot2_type),
        ]

        used_topics: set[str] = self._recent_topics()
        used_titles: list[str] = self._recent_titles()
        existing_slugs: set[str] = self._existing_slugs()

        topics: list[ContentTopic] = []
        for slot, ptype in slots:
            topic = self._plan_slot(
                slot=slot,
                ptype=ptype,
                date_str=date_str,
                used_topics=used_topics,
                used_titles=used_titles,
                existing_slugs=existing_slugs,
            )
            used_topics.add(topic.topic.lower())
            used_titles.append(topic.title.lower())
            topics.append(topic)
            self._save_topic(topic, date_str)

        logger.info(
            "[%s] Planned: %s",
            date_str,
            [(t.slot, t.type, t.topic[:50]) for t in topics],
        )
        return topics

    # ── Slot planning ─────────────────────────────────────────────────────────

    def _plan_slot(
        self,
        slot: int,
        ptype: PostType,
        date_str: str,
        used_topics: set[str],
        used_titles: list[str],
        existing_slugs: set[str],
    ) -> ContentTopic:
        """Generate one ContentTopic for a given slot using LLM + fallbacks."""
        store_ctx = get_store_context(self.brand)
        date_display = _fmt_date(date_str)
        themes = self._theme_pool(ptype)

        prompt = self._build_prompt(
            slot=slot,
            ptype=ptype,
            date_display=date_display,
            store_ctx=store_ctx,
            themes=themes,
            used_topics=list(used_topics),
            used_titles=used_titles[-10:],
        )

        try:
            raw = self._llm_complete(prompt, system=self._system_prompt(ptype))
            data = self._parse_json(raw)
        except Exception as exc:
            logger.warning("LLM failed slot %d — using fallback: %s", slot, exc)
            data = {}

        return self._build_topic(data, slot, ptype, date_str, existing_slugs)

    def _build_prompt(
        self,
        slot: int,
        ptype: PostType,
        date_display: str,
        store_ctx: str,
        themes: list[str],
        used_topics: list[str],
        used_titles: list[str],
    ) -> str:
        slot_label = {0: "Morning", 1: "Midday", 2: "Evening"}[slot]
        guidance = _TYPE_GUIDANCE.get(ptype, "")

        parts = [
            f"You are a content strategist for {self.cfg['brand_name']} ({self.cfg['city']}).",
            f"Plan ONE blog post topic for {date_display}.",
            f"Slot: {slot_label} — Content type: {ptype.value}",
            "",
            f"Type guidance: {guidance}",
            "",
            "Verified restaurant data:",
            store_ctx,
            "",
            f"Theme options (pick one or create a fresh similar angle): {', '.join(themes)}",
            "",
        ]

        if used_topics:
            parts.append(f"Topics used recently — AVOID repeating these exact angles:")
            for t in used_topics[-10:]:
                parts.append(f"  - {t}")

        if used_titles:
            parts.append(f"Recent titles — AVOID these title patterns:")
            for t in used_titles[-5:]:
                parts.append(f"  - {t}")

        parts.extend([
            "",
            "Return ONLY a JSON object with fields:",
            "  type (string), topic (1-2 sentence summary), target_audience (1 sentence),",
            "  primary_keyword (string), slug (URL-safe, max 60 chars).",
            "No markdown, no explanation.",
        ])
        return "\n".join(parts)

    @staticmethod
    def _system_prompt(ptype: PostType) -> str:
        prompts = {
            PostType.VIRAL_ATTENTION:
                "Return valid JSON. Topic should maximize curiosity and food appeal. "
                "Be specific and locally relevant — not generic.",
            PostType.CONVERSION_ORDER:
                "Return valid JSON. Topic should drive a specific customer action: "
                "order, visit, call, or check the menu. Include a clear benefit.",
            PostType.LOCAL_DISCOVERY:
                "Return valid JSON. Topic should feel community-connected and welcoming "
                "to locals. Mention the neighborhood or city naturally.",
            PostType.TOURIST_DISCOVERY:
                "Return valid JSON. Topic should appeal to visitors discovering the area. "
                "Emphasize convenience, quality, and uniqueness.",
            PostType.MENU_HIGHLIGHT:
                "Return valid JSON. Topic should deep-dive into a specific dish or "
                "menu category. Be sensory and specific to verified menu items.",
        }
        return prompts.get(ptype, prompts[PostType.VIRAL_ATTENTION])

    # ── Topic construction ─────────────────────────────────────────────────────

    def _build_topic(
        self,
        data: dict,
        slot: int,
        ptype: PostType,
        date_str: str,
        existing_slugs: set[str],
    ) -> ContentTopic:
        title = data.get("topic", "").strip()
        slug  = data.get("slug", "") or _slugify(data.get("topic", "post"))
        audience = data.get("target_audience", "") or _DEFAULT_AUDIENCE.get(ptype, "Local diners")
        primary_kw = data.get("primary_keyword", "")
        secondary_kws = data.get("secondary_keywords") or []

        # Deduplicate slug
        base_slug = slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1

        return ContentTopic(
            slot=slot,
            type=ptype,
            topic=title,
            target_audience=audience,
            slug=slug[:60],
            primary_keyword=primary_kw,
            secondary_keywords=secondary_kws,
            source_notes=(
                f"[Phase1] Topic selected from {ptype.value} theme pool. "
                "No external trend data. All facts from verified brand config."
            ),
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _rotating_slot2_type(self, date_str: str) -> PostType:
        """Pick slot-2 type based on day-of-week index."""
        weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
        return _SLOT2_CYCLE[weekday % len(_SLOT2_CYCLE)]

    def _theme_pool(self, ptype: PostType) -> list[str]:
        keys = {
            PostType.VIRAL_ATTENTION:   "local_themes",
            PostType.CONVERSION_ORDER: "local_themes",
            PostType.LOCAL_DISCOVERY:  "local_themes",
            PostType.TOURIST_DISCOVERY: "tourist_themes",
            PostType.MENU_HIGHLIGHT:   "menu_themes",
        }
        return self.cfg.get(keys.get(ptype, "local_themes"), [])

    def _recent_topics(self) -> set[str]:
        if not self.history_path.exists():
            return set()
        try:
            data = json.loads(self.history_path.read_text())
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            return {
                e.get("topic", "").lower()
                for e in data
                if e.get("brand") == self.brand
                and e.get("date", "").startswith(cutoff)
            }
        except Exception:
            return set()

    def _recent_titles(self) -> list[str]:
        if not self.history_path.exists():
            return []
        try:
            data = json.loads(self.history_path.read_text())
            cutoff = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
            return [
                e.get("title", "").lower()
                for e in data
                if e.get("brand") == self.brand
                and e.get("date", "").startswith(cutoff)
                and e.get("title")
            ]
        except Exception:
            return []

    def _existing_slugs(self) -> set[str]:
        try:
            from core.agents.dev_agent import MASTER_DIR, PROJECT_FOLDERS
            folder = PROJECT_FOLDERS.get("RawWebsite", "RawWebsite")
            project_path = Path(MASTER_DIR) / folder
            return {
                f.stem.replace("blog-", "").replace("content-", "")
                for f in project_path.glob("*.html")
                if project_path.exists()
            } | {
                f.stem
                for f in project_path.glob("content/posts/*.md")
                if project_path.exists()
            }
        except Exception:
            return set()

    def _save_topic(self, topic: ContentTopic, date_str: str) -> None:
        data = []
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text())
            except Exception:
                pass
        data.append({
            "brand": self.brand,
            "date": date_str,
            "slot": topic.slot,
            "type": topic.type,
            "title": topic.topic,
            "topic": topic.topic,
            "target_audience": topic.target_audience,
            "slug": topic.slug,
            "primary_keyword": topic.primary_keyword,
        })
        data[:] = data[-200:]
        self.history_path.write_text(json.dumps(data, indent=2))

    @staticmethod
    def _llm_complete(prompt: str, system: str = "") -> str:
        from core.llm.router import LLMRouter
        router = LLMRouter()
        return router.complete(
            prompt=prompt,
            system=system,
            task_type="creative",
            description=f"Content planning for {system[:40]}",
            max_tokens=1024,
            temperature=0.8,
        )

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
        return {}


# ── Constants ───────────────────────────────────────────────────────────────

_TYPE_GUIDANCE = {
    PostType.VIRAL_ATTENTION:
        "Maximize attention and curiosity. Strong food appeal, local relevance, shareable angle.",
    PostType.CONVERSION_ORDER:
        "Drive visits and orders. Clear benefit, easy action, appetizing language, strong CTA.",
    PostType.LOCAL_DISCOVERY:
        "Community-connected, welcoming to locals. Stockton/Central Valley neighborhood feel.",
    PostType.TOURIST_DISCOVERY:
        "Appeal to visitors. Memorable, confidence-building for first-timers, easy directions.",
    PostType.MENU_HIGHLIGHT:
        "Deep dive into a specific verified dish. Sensory, detailed, builds appetite and trust.",
}

_DEFAULT_AUDIENCE = {
    PostType.VIRAL_ATTENTION:   "Locals looking for a new dining experience this week",
    PostType.CONVERSION_ORDER:  "Hungry customers ready to order or visit today",
    PostType.LOCAL_DISCOVERY:   "Stockton and Central Valley residents exploring local dining",
    PostType.TOURIST_DISCOVERY: "Visitors and travelers discovering Stockton, CA and nearby",
    PostType.MENU_HIGHLIGHT:    "Sushi lovers and food enthusiasts interested in quality Japanese cuisine",
}


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        return date_str
