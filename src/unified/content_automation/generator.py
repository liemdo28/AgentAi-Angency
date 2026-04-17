"""
Content Generator — generates post drafts for all 6 post types.

Phase 1 uses the existing prompt library from core/content/prompts.py
and integrates with the new ContentResearcher for verified data injection.

Output: ContentDraft with all required fields (title, slug, meta_description,
excerpt, body_markdown, CTA, SEO keywords, image_prompt, etc.)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from .models import ContentDraft, ContentPlan, PostType, ValidationResult
from .researcher import ContentResearcher
from .seo_normalizer import SEONormalizer

logger = logging.getLogger("content_automation.generator")

# Map our PostType to the legacy content-type strings used in templates
_POST_TYPE_MAP = {
    PostType.VIRAL_ATTENTION:    "viral",
    PostType.CONVERSION_ORDER:  "conversion",
    PostType.LOCAL_DISCOVERY:   "local_discovery",
    PostType.TOURIST_DISCOVERY: "tourist",
    PostType.MENU_HIGHLIGHT:    "menu",
    PostType.SEASONAL_TREND:    "viral",  # seasonal uses viral-style prompts in Phase 1
}


class ContentGenerator:
    """
    Generates structured blog post drafts using LLM + verified data.

    The generation pipeline:
      1. Gather verified data (researcher)
      2. Build prompt from template + data
      3. Call LLM
      4. Parse structured output
      5. Normalize SEO fields
      6. Return ContentDraft
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand
        self.researcher = ContentResearcher(brand)
        self.seo = SEONormalizer()
        self._post_type_map = _POST_TYPE_MAP

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, plan: ContentPlan) -> ContentDraft:
        """
        Generate a full post draft from a ContentPlan.

        Returns ContentDraft with all fields populated.
        On failure, returns a draft with error state in validation_result.
        """
        logger.info(
            "Generating post: plan_id=%s type=%s topic=%r",
            plan.id, plan.post_type.value, plan.topic,
        )

        try:
            # Gather verified data
            verified = self.researcher.gather(topic=plan.topic)

            # Build generation prompt
            prompt = self._build_prompt(plan, verified)

            # Call LLM
            from core.llm.router import LLMRouter
            router = LLMRouter()
            raw = router.complete(
                prompt=prompt,
                system=self._system_prompt(),
                task_type="creative",
                description=f"Generate {plan.post_type.value} post for {self.brand}",
                max_tokens=4096,
                temperature=0.75,
            )

            # Parse output
            data = self._parse_output(raw, plan)

            # Normalize SEO fields
            data = self.seo.normalize(data)

            draft = ContentDraft(
                plan_id=plan.id,
                title=data.get("title", plan.title),
                slug=data.get("slug", plan.slug),
                meta_description=data.get("meta_description", plan.meta_description),
                excerpt=data.get("excerpt", ""),
                body_markdown=data.get("body_markdown", ""),
                cta_text=data.get("cta_text", "Order Fresh Sushi Tonight"),
                cta_url=data.get("cta_url") or self.researcher.get_verified_cta()["cta_url"],
                seo_title=data.get("seo_title", ""),
                focus_keyword=data.get("focus_keyword", plan.primary_keyword),
                secondary_keywords=data.get("secondary_keywords", plan.secondary_keywords),
                internal_links=data.get("internal_links", []),
                image_prompt=data.get("image_prompt", ""),
                post_type=plan.post_type,
                target_audience=data.get("target_audience", plan.target_audience),
                source_notes=plan.source_notes,
                raw_content=raw,
            )
            logger.info("Draft generated: title=%r slug=%s", draft.title, draft.slug)
            return draft

        except Exception as exc:
            logger.exception("Draft generation failed: %s", exc)
            return self._error_draft(plan, str(exc))

    def generate_from_goal(self, goal: str, post_type: PostType = PostType.VIRAL_ATTENTION) -> ContentDraft:
        """
        Convenience method: generate a draft from a free-text goal.

        Used by the API endpoint when a reviewer sends a feedback/revision request
        without an existing ContentPlan.
        """
        from .planner import ContentPlanner
        planner = ContentPlanner(self.brand)
        plans = planner.plan_day()
        # Pick the slot matching the post_type, or slot 0 as default
        matching = [p for p in plans if p.post_type == post_type]
        plan = matching[0] if matching else plans[0]
        plan.topic = goal
        plan.title = goal[:70]
        return self.generate(plan)

    # ── Prompt building ───────────────────────────────────────────────────────

    def _build_prompt(self, plan: ContentPlan, verified: dict) -> str:
        """Build the user prompt from the plan + verified data."""
        parts = [
            f"Write a {plan.post_type.value.replace('_', ' ')} blog post for Raw Sushi Bar.",
            "",
            "## VERIFIED BUSINESS DATA (facts you MUST use):",
            verified.get("business_data", ""),
            "",
            "## VERIFIED MENU ITEMS (only these dishes are confirmed to exist):",
            verified.get("menu_data", ""),
            "",
            "## LOCAL CONTEXT (Stockton/Central Valley):",
            verified.get("local_context", ""),
            "",
            "## TRAVELER CONTEXT:",
            verified.get("traveler_context", ""),
            "",
            "## VERIFIED CUSTOMER REVIEWS (for tone reference):",
        ]
        for r in verified.get("verified_reviews", []):
            parts.append(f'  - "{r["text"]}"')
        parts.extend([
            "",
            "## CTA LINKS (verified):",
            verified.get("cta_links", ""),
            "",
            "## POST TOPIC ANGLE:",
            plan.topic,
            "",
            "## PRIMARY KEYWORD:",
            plan.primary_keyword,
            "",
            "## SECONDARY KEYWORDS:",
            ", ".join(plan.secondary_keywords),
            "",
            "## YOUR TASK:",
            self._task_for_type(plan.post_type),
            "",
            "Return a JSON object ONLY (no markdown, no explanation) with these exact fields:",
            "  title, slug, meta_description (120-160 chars), excerpt (1-2 sentences),",
            "  body_markdown (full article, 800-1200 words, markdown format),",
            "  cta_text, cta_url, focus_keyword, secondary_keywords (array),",
            "  internal_links (array of URL slugs), image_prompt (for featured image),",
            "  target_audience.",
            "The JSON object must start with { and end with }.",
        ])
        return "\n".join(parts)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a senior content writer for Raw Sushi Bar, a premium Japanese "
            "sushi restaurant in Stockton, CA. You write clear, appetizing, locally-aware "
            "content that helps readers decide to visit or order.\n\n"
            "CRITICAL RULES:\n"
            "- NEVER invent facts not in the verified business data.\n"
            "- NEVER mention unverified prices, hours, or promotions.\n"
            "- NEVER use exaggerated, spammy, or culturally insensitive language.\n"
            "- Avoid AI filler phrases like 'in today's fast-paced world'.\n"
            "- Always keep content restaurant-relevant.\n"
            "- Return ONLY a valid JSON object — no markdown wrapper, no commentary."
        )

    @staticmethod
    def _task_for_type(post_type: PostType) -> str:
        tasks = {
            PostType.VIRAL_ATTENTION:
                "Write a high-attention post with a curiosity-driven headline. "
                "Make readers want to click and share. Focus on emotional food appeal and local relevance. "
                "Include vivid food descriptions, one local angle, and a soft CTA.",
            PostType.CONVERSION_ORDER:
                "Write a conversion-focused post that moves readers toward visiting or ordering. "
                "Emphasize quality, convenience, and freshness. "
                "Include a strong direct CTA tied to a real action (order link or reservation).",
            PostType.LOCAL_DISCOVERY:
                "Write a locally-relevant post that builds trust with Stockton and Central Valley readers. "
                "Be warm, community-aware, and neighborhood-connected. "
                "Highlight what makes Raw Sushi Bar a local favorite.",
            PostType.TOURIST_DISCOVERY:
                "Write for visitors and travelers discovering the area. "
                "Be enthusiastic, informative, and confidence-building for first-timers. "
                "Mention convenience, location, and what makes the experience memorable.",
            PostType.MENU_HIGHLIGHT:
                "Write a deep-dive into a signature dish or menu category. "
                "Be sensory, passionate, and detailed. "
                "Build appetite and trust in the restaurant's craft.",
            PostType.SEASONAL_TREND:
                "Connect the current season or natural context to a dining need. "
                "Make it feel timely and relevant without forcing a trend. "
                "End with a natural, helpful CTA.",
        }
        return tasks.get(post_type, tasks[PostType.VIRAL_ATTENTION])

    # ── Output parsing ────────────────────────────────────────────────────────

    def _parse_output(self, raw: str, plan: ContentPlan) -> dict:
        """Parse JSON from LLM output, apply fallbacks."""
        text = raw.strip()

        # Strip markdown fences
        for fence in ["```json", "```"]:
            if fence in text:
                parts = text.split(fence)
                if len(parts) >= 2:
                    text = parts[1].split("```")[0].strip()
                    break

        # Find JSON object
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                # Apply plan fallbacks
                data.setdefault("title", plan.title)
                data.setdefault("slug", plan.slug)
                data.setdefault("meta_description", plan.meta_description)
                data.setdefault("target_audience", plan.target_audience)
                return data
            except json.JSONDecodeError as exc:
                logger.warning("JSON parse failed: %s — raw: %s", exc, text[:300])

        # Fallback: treat raw as body_markdown
        logger.warning("Could not parse structured JSON — falling back to raw body")
        slug = plan.slug or _slugify(plan.title)
        return {
            "title": plan.title,
            "slug": slug,
            "meta_description": plan.meta_description,
            "excerpt": plan.topic[:200],
            "body_markdown": text,
            "cta_text": "Visit Raw Sushi Bar Tonight",
            "focus_keyword": plan.primary_keyword,
            "target_audience": plan.target_audience,
        }

    # ── Error state ───────────────────────────────────────────────────────────

    def _error_draft(self, plan: ContentPlan, error: str) -> ContentDraft:
        from .models import RiskLevel
        return ContentDraft(
            plan_id=plan.id,
            title=plan.title or "Generation Failed",
            slug=plan.slug or "error",
            meta_description="",
            excerpt="",
            body_markdown=f"## Generation Error\n\nContent generation failed: {error}\n\nPlease retry or contact the content team.",
            seo_title="",
            focus_keyword=plan.primary_keyword,
            post_type=plan.post_type,
            target_audience=plan.target_audience,
            source_notes=plan.source_notes,
            validation_result=ValidationResult(
                passed=False,
                risk_level=RiskLevel.HIGH,
                hard_valid=False,
                hard_issues=[f"Generation failed: {error}"],
                quality_score=0.0,
                publish_decision="FAIL",
                editor_notes="LLM generation failed. Content requires manual intervention.",
            ),
        )


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")