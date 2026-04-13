"""
Content Generator — generates blog post HTML using Claude + brand templates.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from core.content.store_data import get_brand_config, get_store_context
from core.content.templates import get_template

logger = logging.getLogger("content.generator")


class ContentGenerator:
    """Generates complete blog post HTML files."""

    def generate(self, brand: str, project_id: str, topic: dict) -> dict:
        """Generate a complete HTML blog post.

        Args:
            brand: "bakudan" or "raw"
            project_id: "BakudanWebsite_Sub" or "RawWebsite"
            topic: dict from ContentPlanner with title, slug, key_points, etc.

        Returns:
            {
                "html": "<complete HTML page>",
                "filename": "blog-slug-name.html",
                "word_count": 1050,
                "title": "...",
                "slug": "...",
            }
        """
        cfg = get_brand_config(brand)
        if not cfg:
            raise ValueError(f"Unknown brand: {brand}")

        # Generate article body via Claude
        article_body = self._generate_article_body(cfg, topic)

        # Inject into template
        html = self._assemble_html(brand, cfg, topic, article_body)

        # Calculate word count
        clean_text = re.sub(r"<[^>]+>", " ", article_body)
        word_count = len(clean_text.split())

        filename = f"blog-{topic['slug']}.html"

        return {
            "html": html,
            "filename": filename,
            "word_count": word_count,
            "title": topic["title"],
            "slug": topic["slug"],
            "meta_description": topic.get("meta_description", ""),
        }

    def _generate_article_body(self, cfg: dict, topic: dict) -> str:
        """Call Claude to generate the article body HTML."""
        store_context = get_store_context(topic.get("brand", ""))

        prompt = f"""Write a blog post for {cfg['brand_name']}.

TOPIC: {topic['title']}
SUBTITLE: {topic.get('subtitle', '')}
CONTENT TYPE: {topic.get('content_type', 'general')}
TARGET AUDIENCE: {topic.get('target_audience', 'general readers')}

KEY POINTS TO COVER:
{chr(10).join('- ' + p for p in topic.get('key_points', []))}

RESTAURANT INFORMATION:
{store_context}

WRITING GUIDELINES:
- Brand tone: {cfg.get('brand_tone', 'professional and engaging')}
- Word count: {topic.get('word_count_target', 1000)} words
- Use HTML formatting: <h2>, <h3>, <p>, <ul>, <li>, <blockquote>
- Include 3-5 <h2> subheadings that break up the content
- Make it SEO-friendly with natural keyword usage
- Include specific details about the restaurant (real addresses, real dishes)
- End with a compelling call-to-action
- Do NOT include <html>, <head>, <body> tags — only the article content
- Do NOT use placeholder text — use REAL restaurant data

OUTPUT: Write ONLY the HTML content that goes inside the <article> tag. Start with the first <h2> heading."""

        try:
            from core.llm.router import LLMRouter
            router = LLMRouter()
            result = router.complete(
                prompt=prompt,
                system=(
                    f"You are a professional food and travel writer creating content for {cfg['brand_name']}. "
                    f"Write engaging, accurate, SEO-optimized blog content. "
                    f"Use real restaurant data — never make up addresses, phone numbers, or menu items. "
                    f"Output clean HTML only."
                ),
                task_type="creative",
                description=f"Generate blog article for {cfg['brand_name']}",
                max_tokens=4096,
                temperature=0.75,
            )
            return self._clean_article_html(result)
        except Exception as exc:
            logger.exception("Article generation failed: %s", exc)
            return f"<h2>{topic['title']}</h2><p>Content generation failed: {exc}</p>"

    def _clean_article_html(self, raw: str) -> str:
        """Clean up LLM output — remove markdown wrappers, fix common issues."""
        text = raw.strip()
        # Remove markdown code block if present
        if text.startswith("```html"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        # Remove any accidentally included full-page tags
        for tag in ["<!DOCTYPE", "<html", "</html>", "<head", "</head>", "<body", "</body>"]:
            if tag.lower() in text.lower():
                # Find and remove up to and including the tag
                idx = text.lower().find(tag.lower())
                end = text.find(">", idx)
                if end > idx:
                    text = text[:idx] + text[end + 1:]

        return text.strip()

    def _assemble_html(self, brand: str, cfg: dict, topic: dict, article_body: str) -> str:
        """Inject article body into the brand template."""
        template = get_template(brand)
        now = datetime.now()

        # Estimate reading time
        clean_text = re.sub(r"<[^>]+>", " ", article_body)
        word_count = len(clean_text.split())
        reading_time = max(3, round(word_count / 200))

        # Build template variables
        vars_dict = {
            "title": topic["title"],
            "meta_description": topic.get("meta_description", "")[:160],
            "section_tag": topic.get("section_tag", topic.get("content_type", "Blog")),
            "subtitle": topic.get("subtitle", ""),
            "reading_time": str(reading_time),
            "article_body": article_body,
            "year": str(now.year),
            "date_published": now.strftime("%Y-%m-%d"),
            "date_display": now.strftime("%B %d, %Y"),
            "filename": f"blog-{topic['slug']}.html",
            "keywords": topic.get("keywords", ""),
        }

        # Use safe string formatting (not .format() which conflicts with CSS braces)
        html = template
        for key, value in vars_dict.items():
            html = html.replace(f"{{{key}}}", str(value))

        return html
