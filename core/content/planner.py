"""
Content Planner — decides what topic to write about.
Uses Claude to generate unique, SEO-friendly topics based on brand, content type, and history.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from core.content.store_data import get_brand_config, get_store_context, get_verified_business_data, get_verified_menu_data
from core.content.prompts import ROTATION_POLICY, get_evening_type

logger = logging.getLogger("content.planner")

CONTENT_TYPE_GUIDANCE = {
    "viral": "High-attention post. Maximize clicks and curiosity. Emotional pull, food appeal, local relevance.",
    "conversion": "Convert readers to customers. Emphasize convenience, appetite appeal, decision clarity. Strong CTA.",
    "local_discovery": "Locally relevant. Build trust with nearby audiences. Neighborhood-aware, welcoming.",
    "tourist_discovery": "For visitors and travelers. Memorable, convenient, confidence-building for first-timers.",
    "menu_highlight": "Menu highlights and brand trust. Signature items, sensory descriptions, quality signals.",
    # Legacy mappings
    "tourist": "Write for visitors and travelers discovering the city. Help them find great food. Be enthusiastic and informative.",
    "local": "Write for regular local customers and the community. Be warm, personal, community-focused.",
    "menu": "Deep-dive into a menu item, cooking technique, or ingredient. Be detailed and passionate about the craft.",
}


class ContentPlanner:
    """Plans blog post topics using LLM."""

    def __init__(self, history_path: str | None = None):
        self.history_path = Path(history_path or "data/content_history.json")

    def plan_topic(self, brand: str, content_type: str, project_id: str) -> dict:
        """Generate a topic for a blog post.

        Returns:
            {
                "title": "Best Ramen Spots Near the Riverwalk",
                "slug": "best-ramen-near-riverwalk",
                "meta_description": "Discover authentic...",
                "section_tag": "San Antonio Dining",
                "subtitle": "Your guide to...",
                "content_type": "tourist",
                "target_audience": "Tourists visiting San Antonio",
                "key_points": ["point1", "point2", ...],
                "keywords": "ramen, san antonio, riverwalk, japanese food",
                "word_count_target": 1000,
            }
        """
        cfg = get_brand_config(brand)
        if not cfg:
            raise ValueError(f"Unknown brand: {brand}")

        store_context = get_store_context(brand)
        recent_topics = self._load_recent_topics(brand)
        existing_slugs = self._scan_existing_posts(project_id)

        # Theme suggestions from config
        themes = cfg.get(f"{content_type}_themes", cfg.get("menu_themes", []))

        prompt = self._build_planning_prompt(
            cfg, content_type, store_context, recent_topics, existing_slugs, themes
        )

        # Call LLM
        try:
            from core.llm.router import LLMRouter
            router = LLMRouter()
            result = router.complete(
                prompt=prompt,
                system=(
                    f"You are a content strategist for {cfg['brand_name']}. "
                    "Return ONLY a valid JSON object with these fields: "
                    "title, slug, meta_description, section_tag, subtitle, "
                    "target_audience, key_points (array), keywords (comma-separated string), word_count_target (int)."
                ),
                task_type="creative",
                description=f"Plan blog topic for {brand} ({content_type})",
                max_tokens=1024,
                temperature=0.8,
            )

            # Parse JSON from response
            topic = self._parse_topic_json(result)
            topic["content_type"] = content_type
            topic["brand"] = brand

            # Verify slug doesn't collide
            if topic["slug"] in existing_slugs:
                topic["slug"] = topic["slug"] + f"-{datetime.now().strftime('%m%d')}"

            return topic

        except Exception as exc:
            logger.exception("Topic planning failed: %s", exc)
            # Fallback: generate a simple topic
            return self._fallback_topic(cfg, content_type)

    def _build_planning_prompt(self, cfg: dict, content_type: str,
                                store_context: str, recent_topics: list,
                                existing_slugs: set, themes: list) -> str:
        parts = [
            f"Plan a blog post for {cfg['brand_name']}.",
            f"Content type: {content_type} — {CONTENT_TYPE_GUIDANCE.get(content_type, '')}",
            "",
            "Restaurant info:",
            store_context,
            "",
            f"Theme suggestions (pick one or create your own): {', '.join(themes[:5])}",
        ]

        if recent_topics:
            parts.append(f"\nRecent topics to AVOID (do not repeat): {', '.join(recent_topics[:10])}")

        if existing_slugs:
            parts.append(f"\nExisting blog slugs (do not duplicate): {', '.join(list(existing_slugs)[:15])}")

        parts.append(f"\nToday's date: {datetime.now().strftime('%B %d, %Y')}")
        parts.append("Current season and any relevant events should inform the topic.")
        parts.append("\nReturn a JSON object with: title, slug, meta_description (120-160 chars), "
                     "section_tag (2-3 words), subtitle (1 sentence), target_audience, "
                     "key_points (5-7 bullet points), keywords (comma-separated), word_count_target (800-1200).")

        return "\n".join(parts)

    def _parse_topic_json(self, raw: str) -> dict:
        """Extract JSON from LLM response (may have markdown wrapping)."""
        text = raw.strip()
        # Remove markdown code blocks if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise ValueError(f"Could not parse JSON from: {text[:200]}")

    def _fallback_topic(self, cfg: dict, content_type: str) -> dict:
        """Generate a deterministic fallback topic."""
        now = datetime.now()
        month = now.strftime("%B")
        brand = cfg["brand_name"]

        titles = {
            "tourist": f"Discover {brand}: A Visitor's Guide to {cfg['city']}",
            "local": f"Why {cfg['city']} Locals Love {brand}",
            "menu": f"Behind the Menu: What Makes {brand} Special",
        }
        title = titles.get(content_type, f"{brand} — {month} Update")
        slug = title.lower().replace(" ", "-").replace(":", "").replace("'", "")[:60]

        return {
            "title": title,
            "slug": slug,
            "meta_description": f"Explore {brand} in {cfg['city']}. {cfg['cuisine']} made with passion.",
            "section_tag": content_type.capitalize(),
            "subtitle": f"Your guide to {brand}",
            "content_type": content_type,
            "brand": cfg.get("brand_short", ""),
            "target_audience": f"{content_type} audience",
            "key_points": [f"Visit {brand}", f"Located in {cfg['city']}", "Authentic cuisine"],
            "keywords": f"{brand.lower()}, {cfg['city'].lower()}, {cfg['cuisine'].lower()}",
            "word_count_target": 1000,
        }

    def _load_recent_topics(self, brand: str) -> list:
        """Load recent topic titles from history."""
        try:
            if self.history_path.exists():
                data = json.loads(self.history_path.read_text())
                return [
                    e["title"] for e in data
                    if e.get("brand") == brand
                ][-15:]
        except Exception:
            pass
        return []

    def _scan_existing_posts(self, project_id: str) -> set:
        """Scan project directory for existing blog-*.html files."""
        from core.agents.dev_agent import MASTER_DIR, PROJECT_FOLDERS
        folder = PROJECT_FOLDERS.get(project_id, project_id)
        project_path = MASTER_DIR / folder
        slugs = set()
        if project_path.exists():
            for f in project_path.glob("blog-*.html"):
                slug = f.stem.replace("blog-", "")
                slugs.add(slug)
        return slugs

    def save_to_history(self, topic: dict) -> None:
        """Append a generated topic to history."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        data = []
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text())
            except Exception:
                data = []
        data.append({
            **topic,
            "generated_at": datetime.now().isoformat(),
        })
        # Keep last 100 entries
        data = data[-100:]
        self.history_path.write_text(json.dumps(data, indent=2))
