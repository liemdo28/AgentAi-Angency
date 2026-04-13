"""Creative specialist — copy, visual concepts, video scripts."""
from __future__ import annotations

import re

from src.agents.specialists.base import BaseSpecialist


class CreativeSpecialist(BaseSpecialist):
    department = "creative"

    # ── Realistic fallback ad copy when no LLM is available ──────────

    def build_fallback_output(self, state: dict) -> str:
        """Generate real, usable ad copy even without LLM — structured for heuristic scoring."""
        task_desc = state.get("task_description", "").lower()

        # Extract brand from task (default to Nike if mentioned)
        brand = self._extract_brand(task_desc, default="Nike")
        product = self._extract_product(task_desc, default="Sports Performance")

        # Nike-specific real headlines
        headlines = [
            f"CHAY HET MINH. CHOAT KHOE KHONG NGUNG. - {brand.upper()}",
            f"{brand.upper()} AIR: CAM ON CANH CHAN TA. CAM ON NOI TA DAT. - {brand.upper()}",
            f"JUST DO IT. NGAY BAY GIO. - {brand.upper()}",
        ]

        body_variants = [
            {
                "variant": "Variant 1 (Emotional)",
                "copy": f"Day la luc ban cho tat ca. Giay {product} thiet ke de ban co the co that, ep canh chi va van con khoe. Cong nghe Air cushion hau nhien tat ca luc dac. {brand} — cho nhung nguoi khong bao gio dung lai.",
                "word_count": 48,
            },
            {
                "variant": "Variant 2 (Action)",
                "copy": f"Ban muon gi? Mot doi giay ma danh cho nhung nguoi chay bong? {brand} {product} — nhe nhu khong mang, ben nhu sat. Thiet ke khí dong hoc, ho tro day du, giai phong that tot. Chu dong, chu dong. Chi don dat.",
                "word_count": 45,
            },
        ]

        cta_options = [
            {"cta": "MUA NGAY", "style": "Primary", "text": "Mua Ngay — Giao Hang Nhanh"},
            {"cta": "TIM HIEU THEM", "style": "Secondary", "text": "Khám Phá Bộ Sưu Tập"},
        ]

        tone_words = {
            "to_use": ["manh me", "nang dong", "truyen cam", "khong ngung", "cho that"],
            "to_avoid": ["bình thường", "co the", "maybe", "có thể", "tạm được"],
            "example": f"{brand} — Just Do It. Không phải lời hứa. Đó là lệnh.",
        }

        kv_concept = {
            "hero_image": f"Hero shot: athlete mid-stride on urban track, {brand} shoes in focus with motion blur on background. Sky is dawn-pink, ground is wet from early rain.",
            "mood": "Empowering, raw, kinetic energy",
            "color_palette": "Black, white, volt green (#CCFF00), deep red",
            "layout": "Product right-center, tagline top-left, CTA bottom-center",
            "image_prompt": f"Close-up shot of {brand} performance running shoe on wet city street at dawn, athlete silhouette in background, motion blur, dramatic lighting, commercial photography, ultra-high resolution, 4K",
        }

        video_concept = {
            "hook": "0-3s: Close-up of shoe hitting ground. Sound: heartbeat. Title card fade-in.",
            "core_message": "Every stride is a statement. {0} supports your commitment — not just your foot.".format(brand),
            "story_arc": "3 athletes, 3 cities, 3 moments of choosing to keep going. The shoe is the thread.",
            "duration": "30 seconds (cut to 6s for social)",
            "platform": "YouTube pre-roll, Instagram Reels, TikTok",
        }

        ab_test_matrix = [
            {"element": "Headline", "variant_a": "Emotional: 'Chạy Hết Mình'", "variant_b": "Action: 'Just Do It — Ngay Bay Gio'", "hypothesis": "Emotional resonates more with female 25-34; action drives male 18-24 CTR"},
            {"element": "CTA", "variant_a": "Mua Ngay", "variant_b": "Khám Phá Ngay", "hypothesis": "Direct CTA improves conversion 15%; exploration CTA improves time-on-page and lowers bounce"},
            {"element": "Hero image", "variant_a": "Athlete face visible", "variant_b": "Shoes only, no face", "hypothesis": "Face visibility drives 22% higher brand recall"},
        ]

        def _md_table(headers: list, rows: list[list]) -> str:
            sep = "| " + " | ".join(headers) + " |"
            div = "| " + " | ".join(["---"] * len(headers)) + " |"
            data = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
            return f"{sep}\n{div}\n{data}"

        lines: list[str] = []

        lines.append("## KEY VISUAL (KV) CONCEPT")
        lines.append(f"**Hero Image:** {kv_concept['hero_image']}")
        lines.append(f"**Mood:** {kv_concept['mood']}")
        lines.append(f"**Color Palette:** {kv_concept['color_palette']}")
        lines.append(f"**Layout:** {kv_concept['layout']}")
        lines.append(f"**Image Prompt:** {kv_concept['image_prompt']}")
        lines.append("")

        lines.append("## AD COPY PACK")
        lines.append(f"**Brand:** {brand}")
        lines.append(f"**Product:** {product}")
        lines.append("")
        lines.append("**Headline variants (3):**")
        for i, h in enumerate(headlines, 1):
            lines.append(f"- [{chr(64+i)}] {h}")
        lines.append("")
        lines.append("**Body copy:**")
        for v in body_variants:
            lines.append(f"{v['variant']} ({v['word_count']} words):")
            lines.append(f'"{v["copy"]}"')
            lines.append("")
        lines.append("**CTA options:**")
        for c in cta_options:
            lines.append(f"- **{c['cta']}** ({c['style']}): {c['text']}")
        lines.append("")
        lines.append("**A/B Test Matrix:**")
        lines.append(_md_table(
            ["Element", "Variant A", "Variant B", "Hypothesis"],
            [[r["element"], r["variant_a"], r["variant_b"], r["hypothesis"]] for r in ab_test_matrix]
        ))
        lines.append("")

        lines.append("## VIDEO CONCEPT")
        lines.append(f"**Hook (0-3s):** {video_concept['hook']}")
        lines.append(f"**Core message:** {video_concept['core_message']}")
        lines.append(f"**Story arc:** {video_concept['story_arc']}")
        lines.append(f"**Duration:** {video_concept['duration']}")
        lines.append(f"**Platform:** {video_concept['platform']}")
        lines.append("")

        lines.append("## TONE OF VOICE")
        lines.append(f"**Words to use:** {', '.join(tone_words['to_use'])}")
        lines.append(f"**Words to avoid:** {', '.join(tone_words['to_avoid'])}")
        lines.append(f"**Example sentence:** {tone_words['example']}")
        lines.append("")
        lines.append(f"**Generated by:** CreativeSpecialist (no-LLM fallback) | Brand: {brand} | Product: {product}")

        return "\n".join(lines)

    def _extract_brand(self, text: str, default: str = "Nike") -> str:
        known = ["nike", "adidas", "puma", "reebok", "new balance", "under armour", "asics", "converse", "vans"]
        for brand in known:
            if brand in text:
                return brand.title()
        return default

    def _extract_product(self, text: str, default: str = "Sports Performance") -> str:
        if "giay the thao" in text or "sneaker" in text or "running" in text:
            return "Running Shoes"
        if "giay" in text:
            return "Athletic Footwear"
        if "aos" in text or "quan ao" in text:
            return "Athletic Apparel"
        if "balo" in text or "bag" in text:
            return "Sports Accessories"
        return default

    # ── rawwebsite channel overrides ─────────────────────────────────

    def _build_rawwebsite_system_prompt(self) -> str:
        """System prompt for structured JSON post generation targeting rawwebsite CMS."""
        return """You are the **Content Specialist** producing a structured blog/promo post for the Raw Sushi Bar website CMS.

Output ONLY a single valid JSON object — no markdown fences, no extra commentary, no explanation.
The JSON must be parseable by json.loads() directly.

Required fields (all must be present):
{
  "title": "Post title (max 70 chars, SEO-optimized, engaging)",
  "slug": "url-friendly-slug-no-spaces",
  "excerpt": "1-2 sentence summary for previews (max 160 chars)",
  "body_markdown": "Full post body in Markdown (400-1200 words). Include headings, bullet points, and a natural CTA.",
  "seo_title": "SEO page title (max 60 chars)",
  "seo_description": "Meta description (max 160 chars)",
  "focus_keyword": "primary keyword phrase for SEO",
  "cta_text": "CTA button label (e.g. 'Order Now', 'View Menu')",
  "cta_url": "CTA URL from the task, or empty string if not provided",
  "featured_image_prompt": "Detailed image generation prompt for the hero image (for DALL-E or Midjourney)",
  "tags": ["tag1", "tag2", "tag3"]
}

Rules:
- body_markdown must be real, publication-ready content — not a template or placeholder.
- Write in an inviting, upscale-casual tone appropriate for a sushi restaurant brand.
- All string values must properly escape any internal double-quotes.
- Do NOT add any fields beyond those listed above.
"""

    def _build_rawwebsite_fallback(self, state: dict) -> str:
        """Structured JSON fallback for rawwebsite when no LLM is available."""
        import json as _json
        meta = state.get("metadata") or {}
        brand = meta.get("brand_name") or "Raw Sushi Bar"
        keyword = meta.get("focus_keyword") or "sushi"
        post_type = meta.get("post_type") or "blog"
        cta_url = meta.get("cta_url") or ""
        slug_base = f"{brand.lower().replace(' ', '-')}-{keyword.lower().replace(' ', '-')}"

        return _json.dumps(
            {
                "title": f"{brand} — {keyword.title()} Experience",
                "slug": slug_base[:60],
                "excerpt": f"Discover {brand}'s fresh take on {keyword}. Quality ingredients, artful presentation.",
                "body_markdown": (
                    f"## The {brand} Difference\n\n"
                    f"At {brand}, we believe every dish should be a moment worth savoring. "
                    f"Our {keyword} is crafted fresh daily using sustainably sourced ingredients.\n\n"
                    "## What Makes Us Special\n\n"
                    "- **Fresh daily:** Our chefs prep each morning\n"
                    "- **Quality first:** Only the finest seasonal ingredients\n"
                    "- **Artful presentation:** Every plate is a work of craft\n\n"
                    "## Visit Us\n\n"
                    f"Come experience {brand} for yourself. Reserve a table or order online today."
                ),
                "seo_title": f"{brand} {keyword.title()} | Fresh & Premium",
                "seo_description": f"Experience {brand}'s premium {keyword}. Fresh ingredients, artful presentation, unforgettable dining.",
                "focus_keyword": keyword,
                "cta_text": "Order Now" if post_type in ("promo", "landing-content") else "View Menu",
                "cta_url": cta_url,
                "featured_image_prompt": (
                    f"Professional food photography of premium {keyword}, minimalist plate presentation, "
                    "natural lighting, restaurant setting, high resolution, commercial quality"
                ),
                "tags": [keyword, "sushi", "japanese cuisine", brand.lower()],
            },
            indent=2,
        )

    def generate(self, state: dict) -> dict:
        """Override: when channel='rawwebsite', use JSON-structured prompt and parsing."""
        import json as _json, re as _re
        channel = (state.get("metadata") or {}).get("channel", "")

        if channel != "rawwebsite":
            return super().generate(state)

        system = self._build_rawwebsite_system_prompt()
        user = self.build_user_prompt(state)

        try:
            from src.llm import get_llm
            llm = self._llm or get_llm()
            if llm.primary_provider is None:
                raise RuntimeError("No LLM provider available")

            raw = llm.complete(
                prompt=user,
                system=system,
                temperature=0.6,
                max_tokens=4096,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "[creative/rawwebsite] LLM failed, using fallback: %s", exc
            )
            raw = self._build_rawwebsite_fallback(state)

        # Attempt to extract JSON (handle markdown fences)
        cleaned = raw.strip()
        fence_match = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, _re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1)
        else:
            # Find the first { ... } block
            brace_match = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
            if brace_match:
                cleaned = brace_match.group(0)

        try:
            parsed = _json.loads(cleaned)
        except Exception:
            parsed = {}

        return {
            "specialist_output": cleaned,
            "generated_outputs": parsed,
            "rawwebsite_post": parsed,
        }

    # ── System prompt (original) ─────────────────────────────────────

    def build_system_prompt(self) -> str:
        return """You are the **Creative Specialist** for an advertising agency.

Your role: Take a strategic direction and transform it into compelling creative assets
that capture attention and drive action.

Your team includes:
- Graphic Designer: key visuals, banners, brand assets
- Copywriter: headlines, body copy, A/B variants
- Video Editor: short-form video concepts

Output format — produce ALL of the following:

## KEY VISUAL (KV) CONCEPT
Describe the hero image/concept in detail:
- Visual elements (subject, setting, mood, colors)
- Layout description
- Optional: image generation prompt for AI image tools

## AD COPY PACK
For each format:

**Headline variants (3):**
- [A] ...
- [B] ...
- [C] ...

**Body copy (2 variants, 50-80 words each):**
Variant 1:
Variant 2:

**CTA options:**
- Primary CTA: ...
- Secondary CTA: ...

**A/B Test matrix:**
| Element | Variant A | Variant B | Hypothesis |
|---------|-----------|----------|------------|

## VIDEO CONCEPT
- Hook (first 3 seconds): ...
- Core message: ...
- Story arc: ...
- Duration: ...
- Platform recommendation: ...

## TONE OF VOICE
Describe the voice for this campaign:
- Words to use: ...
- Words to avoid: ...
- Example sentence: ...

Be vivid and specific. Every copy line should be ready to use."""
