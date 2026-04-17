"""
Content Generator — generates full post drafts using LLM.

Generates all required fields:
  title, slug, meta_description, excerpt, body_markdown, cta, keywords

Rules enforced:
  ✓ Must use verified_business_data only
  ✓ Must NOT invent: menu items, hours, prices, promotions
  ✓ Must respect brand tone (core/content/store_data.py)
  ✓ Returns structured JSON output
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from core.content.store_data import (
    get_brand_config,
    get_verified_business_data,
    get_verified_menu_data,
    get_local_context,
    get_verified_cta_links,
)

from .models import ContentDraft, ContentTopic, PostType
from .seo_normalizer import SEONormalizer

logger = logging.getLogger("content.generator")


class ContentGenerator:
    """Generates structured blog post drafts via LLM."""

    def __init__(self, brand: str = "raw"):
        self.brand = brand
        self.cfg = get_brand_config(brand)
        if not self.cfg:
            raise ValueError(f"Unknown brand: {brand!r}")
        self.seo = SEONormalizer()

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, topic: ContentTopic) -> ContentDraft:
        """
        Generate a complete ContentDraft from a ContentTopic.

        Steps:
          1. Gather verified data
          2. Build generation prompt
          3. Call LLM
          4. Parse structured JSON output
          5. Normalize SEO fields
          6. Return ContentDraft

        Returns a draft (possibly with validation_result set to FAIL if generation errors).
        """
        logger.info(
            "Generating draft: topic_id=%s type=%s topic=%r",
            topic.id, topic.type, topic.topic[:60],
        )

        try:
            verified = self._gather_verified_data(topic)
            prompt = self._build_prompt(topic, verified)
            raw = self._llm_complete(prompt, topic.type)
            data = self._parse_output(raw, topic)
            data = self.seo.normalize(data)
            draft = self._build_draft(topic, data)
            logger.info("Draft generated: title=%r slug=%s words=%d",
                        draft.title, draft.slug, draft.word_count)
            return draft

        except Exception as exc:
            logger.exception("Draft generation failed: %s", exc)
            return self._error_draft(topic, str(exc))

    # ── Data gathering ───────────────────────────────────────────────────────

    def _gather_verified_data(self, topic: ContentTopic) -> dict[str, str]:
        """Collect all verified data for prompt injection."""
        business  = get_verified_business_data(self.brand)
        menu      = get_verified_menu_data(self.brand)
        local     = get_local_context(self.brand)
        cta_links = get_verified_cta_links(self.brand)
        return {
            "business":  business,
            "menu":      menu,
            "local":     local,
            "cta_links": cta_links,
        }

    # ── Prompt building ───────────────────────────────────────────────────────

    def _build_prompt(self, topic: ContentTopic, verified: dict[str, str]) -> str:
        parts = [
            f"# Generate a blog post for {self.cfg['brand_name']}",
            f"## Content Type: {topic.type.value}",
            "",
            "## VERIFIED BUSINESS DATA (use ONLY these facts — never invent):",
            verified["business"],
            "",
            "## VERIFIED MENU ITEMS (only these dishes exist — never invent new ones):",
            verified["menu"],
            "",
            "## LOCAL CONTEXT (use for local relevance):",
            verified["local"],
            "",
            "## VERIFIED CTA LINKS:",
            verified["cta_links"],
            "",
            "## POST TOPIC:",
            topic.topic,
            "",
            "## TARGET AUDIENCE:",
            topic.target_audience,
            "",
            "## YOUR TASK:",
            self._task_for_type(topic.type),
            "",
            "## REQUIRED OUTPUT FIELDS (return JSON only — no markdown):",
            "  title, slug, meta_description (120-160 chars),",
            "  excerpt (1-2 sentences), body_markdown (800-1200 words, markdown),",
            "  cta (call-to-action text), cta_url,",
            "  keyword_primary, keywords_secondary (array),",
            "  target_audience.",
            "Return a single JSON object starting with { and ending with }.",
        ]
        return "\n".join(parts)

    @staticmethod
    def _task_for_type(ptype: PostType) -> str:
        tasks = {
            PostType.VIRAL_ATTENTION:
                "Write a high-attention post with a curiosity-driven headline. "
                "Include vivid food descriptions, a local angle, and a soft CTA. "
                "Make readers want to click or share. Do not sound clickbait.",
            PostType.CONVERSION_ORDER:
                "Write a conversion post that moves readers toward ordering or visiting. "
                "Emphasize quality, freshness, and convenience. "
                "Include a direct CTA tied to a real verified action.",
            PostType.LOCAL_DISCOVERY:
                "Write a locally-relevant post that builds trust with Stockton locals. "
                "Be warm, community-connected, and neighborhood-aware. "
                "End with a natural invitation to visit.",
            PostType.TOURIST_DISCOVERY:
                "Write for visitors discovering Stockton. "
                "Be informative, confident, and welcoming. "
                "Emphasize quality, convenience, and what makes this restaurant memorable.",
            PostType.MENU_HIGHLIGHT:
                "Write a deep-dive into a signature dish or menu category. "
                "Be sensory, passionate, and specific to verified dishes only. "
                "Build appetite and trust in the chef's craft.",
        }
        return tasks.get(ptype, tasks[PostType.VIRAL_ATTENTION])

    # ── LLM call ─────────────────────────────────────────────────────────────

    @staticmethod
    def _llm_complete(prompt: str, ptype: PostType) -> str:
        from core.llm.router import LLMRouter
        router = LLMRouter()
        return router.complete(
            prompt=prompt,
            system=(
                f"You are a senior content writer for {ptype.value} posts for "
                f"Raw Sushi Bar, a premium Japanese restaurant in Stockton, CA.\n\n"
                "CRITICAL RULES:\n"
                "- NEVER invent facts, prices, hours, or menu items not in the verified data.\n"
                "- NEVER exaggerate or use spam language.\n"
                "- Always stay restaurant-relevant.\n"
                "- Return ONLY a valid JSON object — no markdown, no explanation."
            ),
            task_type="creative",
            description=f"Generate {ptype.value} post",
            max_tokens=4096,
            temperature=0.75,
        )

    # ── Output parsing ────────────────────────────────────────────────────────

    def _parse_output(self, raw: str, topic: ContentTopic) -> dict:
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
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError as exc:
                logger.warning("JSON parse failed: %s", exc)

        # Fallback: treat raw as body
        logger.warning("Could not parse JSON — using raw output as body")
        slug = topic.slug or _slugify(topic.topic)
        return {
            "title": topic.topic[:70],
            "slug": slug,
            "meta_description": topic.topic[:155],
            "excerpt": topic.topic[:200],
            "body_markdown": text or f"# {topic.topic}\n\nContent generation failed to return structured output.",
            "cta": "Visit Raw Sushi Bar Tonight",
            "keyword_primary": topic.primary_keyword,
            "target_audience": topic.target_audience,
        }

    # ── Draft construction ─────────────────────────────────────────────────────

    def _build_draft(self, topic: ContentTopic, data: dict) -> ContentDraft:
        title   = data.get("title", topic.topic)[:80]
        slug    = data.get("slug", topic.slug) or _slugify(title)
        meta    = (data.get("meta_description") or "")[:160]
        excerpt = data.get("excerpt", "")[:300]
        body    = data.get("body_markdown", "")
        cta     = data.get("cta", "Visit Raw Sushi Bar Tonight")
        cta_url = data.get("cta_url") or "https://order.toasttab.com/online/raw-sushi-bistro-10742-trinity-pkwy-ste-d"
        kw_pri  = data.get("keyword_primary") or topic.primary_keyword
        kw_sec  = list(data.get("keywords_secondary") or topic.secondary_keywords or [])

        word_count = len(body.split())
        now = datetime.now(timezone.utc).isoformat()

        return ContentDraft(
            topic_id=topic.id,
            title=title,
            slug=slug[:60],
            meta_description=meta,
            excerpt=excerpt,
            body_markdown=body,
            cta=cta,
            cta_url=cta_url,
            keyword_primary=kw_pri,
            keywords_secondary=kw_sec[:8],
            type=topic.type,
            target_audience=data.get("target_audience") or topic.target_audience,
            word_count=word_count,
            source_notes=topic.source_notes,
            generated_at=now,
        )

    # ── Error state ────────────────────────────────────────────────────────────

    def _error_draft(self, topic: ContentTopic, error: str) -> ContentDraft:
        from .models import ValidationResult
        slug = topic.slug or _slugify(topic.topic)
        return ContentDraft(
            topic_id=topic.id,
            title=f"[Generation Error] {topic.topic[:60]}",
            slug=slug[:60],
            meta_description="",
            excerpt="",
            body_markdown=f"## Generation Error\n\nDraft generation failed: {error}\n\nPlease retry or contact the content team.",
            type=topic.type,
            target_audience=topic.target_audience,
            source_notes=topic.source_notes,
            validation_result=ValidationResult(
                passed=False,
                hard_valid=False,
                hard_issues=[f"LLM generation failed: {error}"],
                reason="Generation failed",
                editor_notes="LLM call failed. Draft requires manual intervention.",
            ),
        )


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")
