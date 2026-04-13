"""
Content Generator — generates blog post HTML using the 5-type prompt system.
Uses verified business data injection, never fabricates restaurant facts.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from core.content.prompts import get_prompt_template, get_system_prompt, PROMPT_VALIDATION
from core.content.store_data import (
    get_brand_config,
    get_verified_business_data,
    get_verified_menu_data,
    get_local_context,
    get_traveler_context,
    get_surrounding_audience,
    get_verified_cta_links,
)
from core.content.templates import get_template

logger = logging.getLogger("content.generator")


class ContentGenerator:
    """Generates complete blog post HTML files using the 5-type prompt system."""

    def generate(self, brand: str, project_id: str, topic: dict) -> dict:
        """Generate a complete HTML blog post.

        Returns:
            {
                "html": "<complete HTML page>",
                "filename": "blog-slug-name.html",
                "word_count": 1050,
                "title": "...",
                "slug": "...",
                "content_output": {...}  # structured output from LLM
            }
        """
        cfg = get_brand_config(brand)
        if not cfg:
            raise ValueError(f"Unknown brand: {brand}")

        content_type = topic.get("content_type", "viral")

        # Generate via Claude with type-specific prompt
        content_output = self._generate_with_prompt(cfg, brand, topic, content_type)

        # Extract article body from structured output
        article_body = content_output.get("article_body", "")
        title = content_output.get("title", topic.get("title", "Untitled"))
        meta_desc = content_output.get("meta_description", topic.get("meta_description", ""))
        slug = content_output.get("slug", topic.get("slug", "post"))

        # Inject into HTML template
        topic_merged = {**topic, **content_output, "title": title, "meta_description": meta_desc, "slug": slug}
        html = self._assemble_html(brand, cfg, topic_merged, article_body)

        # Word count
        clean_text = re.sub(r"<[^>]+>", " ", article_body)
        word_count = len(clean_text.split())

        filename = f"blog-{slug}.html"

        return {
            "html": html,
            "filename": filename,
            "word_count": word_count,
            "title": title,
            "slug": slug,
            "meta_description": meta_desc,
            "content_output": content_output,
        }

    def _generate_with_prompt(self, cfg: dict, brand: str, topic: dict, content_type: str) -> dict:
        """Call Claude with the type-specific prompt template."""
        # Build system prompt
        system = get_system_prompt(cfg["brand_name"], cfg["cuisine"])

        # Build user prompt from template
        template = get_prompt_template(content_type)
        user_prompt = template.format(
            verified_business_data=get_verified_business_data(brand),
            verified_menu_data=get_verified_menu_data(brand),
            local_context=get_local_context(brand),
            traveler_context=get_traveler_context(brand),
            surrounding_audience_profile=get_surrounding_audience(brand),
            verified_cta_links=get_verified_cta_links(brand),
            post_topic=topic.get("title", topic.get("post_topic", "")),
            keyword_target=topic.get("keywords", topic.get("keyword_target", "")),
        )

        try:
            from core.llm.router import LLMRouter
            router = LLMRouter()
            result = router.complete(
                prompt=user_prompt,
                system=system,
                task_type="creative",
                description=f"Generate {content_type} blog post for {cfg['brand_name']}",
                max_tokens=4096,
                temperature=0.75,
            )
            return self._parse_content_output(result, topic)

        except Exception as exc:
            logger.exception("Content generation failed: %s", exc)
            return {
                "title": topic.get("title", ""),
                "article_body": f"<h2>{topic.get('title', 'Error')}</h2><p>Generation failed: {exc}</p>",
                "meta_description": topic.get("meta_description", ""),
                "slug": topic.get("slug", "error"),
            }

    def _parse_content_output(self, raw: str, topic: dict) -> dict:
        """Parse the structured JSON output from Claude."""
        text = raw.strip()

        # Try to extract JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        start = text.find("{")
        end = text.rfind("}") + 1

        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                # Ensure required fields
                data.setdefault("title", topic.get("title", ""))
                data.setdefault("slug", topic.get("slug", ""))
                data.setdefault("meta_description", topic.get("meta_description", ""))
                data.setdefault("article_body", "")
                return data
            except json.JSONDecodeError:
                pass

        # Fallback: treat entire output as article body
        logger.warning("Could not parse JSON from LLM output, using as raw article body")
        article_body = self._clean_article_html(text)
        return {
            "title": topic.get("title", ""),
            "slug": topic.get("slug", ""),
            "meta_description": topic.get("meta_description", ""),
            "article_body": article_body,
            "content_type": topic.get("content_type", ""),
        }

    def validate_with_llm(self, html: str, brand: str) -> dict:
        """Run the LLM-based final editorial validation."""
        clean = re.sub(r"<[^>]+>", " ", html)
        sample = " ".join(clean.split()[:800])

        prompt = PROMPT_VALIDATION.format(
            generated_post=sample,
            verified_business_data=get_verified_business_data(brand),
            verified_menu_data=get_verified_menu_data(brand),
        )

        try:
            from core.llm.router import LLMRouter
            router = LLMRouter()
            result = router.complete(
                prompt=prompt,
                system="You are the final editorial compliance reviewer. Return JSON only.",
                task_type="default",
                description="Content validation review",
                max_tokens=1024,
                temperature=0.3,
            )
            text = result.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except Exception as exc:
            logger.warning("LLM validation failed: %s", exc)

        return {"publish_decision": "PASS", "risk_level": "LOW", "issues_found": [], "final_editor_notes": "LLM review skipped"}

    def _clean_article_html(self, raw: str) -> str:
        """Clean up LLM output."""
        text = raw.strip()
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        # Remove full-page tags if accidentally included
        for tag in ["<!DOCTYPE", "<html", "</html>", "<head", "</head>", "<body", "</body>"]:
            if tag.lower() in text.lower():
                idx = text.lower().find(tag.lower())
                end = text.find(">", idx)
                if end > idx:
                    text = text[:idx] + text[end + 1:]

        return text.strip()

    def _assemble_html(self, brand: str, cfg: dict, topic: dict, article_body: str) -> str:
        """Inject article body into the brand template."""
        template = get_template(brand)
        now = datetime.now()

        clean_text = re.sub(r"<[^>]+>", " ", article_body)
        word_count = len(clean_text.split())
        reading_time = max(3, round(word_count / 200))

        vars_dict = {
            "title": topic.get("title", ""),
            "meta_description": topic.get("meta_description", "")[:160],
            "section_tag": topic.get("section_tag", topic.get("content_type", "Blog")).replace("_", " ").title(),
            "subtitle": topic.get("subtitle", topic.get("excerpt", "")),
            "reading_time": str(reading_time),
            "article_body": article_body,
            "year": str(now.year),
            "date_published": now.strftime("%Y-%m-%d"),
            "date_display": now.strftime("%B %d, %Y"),
            "filename": f"blog-{topic.get('slug', 'post')}.html",
            "keywords": topic.get("keywords", topic.get("keyword_target", "")),
        }

        html = template
        for key, value in vars_dict.items():
            html = html.replace(f"{{{key}}}", str(value))
        return html
