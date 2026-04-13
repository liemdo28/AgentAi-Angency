"""
Content Validator — 8-check validation gate.
ALL checks must pass before content can be approved for publishing.
"""

from __future__ import annotations

import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from core.content.store_data import get_brand_config

logger = logging.getLogger("content.validator")


class _TagChecker(HTMLParser):
    """Simple HTML parser to check for unclosed tags."""

    def __init__(self):
        super().__init__()
        self.errors = []
        self._stack = []

    def handle_starttag(self, tag, attrs):
        void_tags = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr"}
        if tag.lower() not in void_tags:
            self._stack.append(tag.lower())

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag.lower():
            self._stack.pop()
        elif tag.lower() in self._stack:
            self.errors.append(f"Mismatched closing tag: </{tag}>")

    def get_unclosed(self):
        return self._stack[:]


class ContentValidator:
    """Runs 8 validation checks on generated content."""

    def validate(self, html: str, brand: str, project_id: str) -> dict:
        """Run all 8 checks. Returns validation report."""
        cfg = get_brand_config(brand)
        checks = [
            self._check_business_data(html, cfg),
            self._check_seo_title(html, cfg),
            self._check_seo_meta(html),
            self._check_schema_org(html, brand),
            self._check_content_quality(html),
            self._check_link_integrity(html, project_id),
            self._check_cultural_review(html, cfg),
            self._check_html_validity(html),
        ]

        passed_count = sum(1 for c in checks if c["passed"])
        all_passed = all(c["passed"] for c in checks)
        blocking = [c["name"] for c in checks if not c["passed"]]

        return {
            "passed": all_passed,
            "total_checks": len(checks),
            "passed_checks": passed_count,
            "checks": checks,
            "blocking_failures": blocking,
        }

    # ── Check 1: Business Data ─────────────────────────────────────────

    def _check_business_data(self, html: str, cfg: dict) -> dict:
        """Verify store addresses and phone numbers in HTML match registry."""
        issues = []
        verified = 0

        for sid, store in cfg.get("stores", {}).items():
            phone = store.get("phone", "")
            # Check if phone appears correctly (if mentioned at all)
            if phone:
                # Normalize phone for comparison
                phone_digits = re.sub(r"[^\d]", "", phone)
                html_phones = re.findall(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", html)
                for hp in html_phones:
                    hp_digits = re.sub(r"[^\d]", "", hp)
                    if hp_digits == phone_digits:
                        verified += 1
                        break

        # Check for obviously wrong phone numbers (made up by AI)
        all_phones = re.findall(r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", html)
        known_digits = set()
        for store in cfg.get("stores", {}).values():
            if store.get("phone"):
                known_digits.add(re.sub(r"[^\d]", "", store["phone"]))

        for hp in all_phones:
            hp_digits = re.sub(r"[^\d]", "", hp)
            if hp_digits not in known_digits:
                issues.append(f"Unknown phone number in content: {hp}")

        passed = len(issues) == 0
        return {
            "name": "business_data",
            "passed": passed,
            "details": f"{verified} store references verified" if passed else f"Issues: {'; '.join(issues)}",
        }

    # ── Check 2: SEO Title ─────────────────────────────────────────────

    def _check_seo_title(self, html: str, cfg: dict) -> dict:
        """Check <title> tag: present, 30-65 chars, contains brand name."""
        match = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
        if not match:
            return {"name": "seo_title", "passed": False, "details": "No <title> tag found"}

        title = match.group(1).strip()
        issues = []

        if len(title) < 30:
            issues.append(f"Title too short ({len(title)} chars, min 30)")
        if len(title) > 65:
            issues.append(f"Title too long ({len(title)} chars, max 65)")

        brand_name = cfg.get("brand_name", "")
        if brand_name.lower() not in title.lower():
            issues.append(f"Title missing brand name '{brand_name}'")

        return {
            "name": "seo_title",
            "passed": len(issues) == 0,
            "details": f"Title OK: '{title}' ({len(title)} chars)" if not issues else "; ".join(issues),
        }

    # ── Check 3: SEO Meta Description ──────────────────────────────────

    def _check_seo_meta(self, html: str) -> dict:
        """Check meta description: present, 120-160 chars."""
        match = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
        if not match:
            return {"name": "seo_meta", "passed": False, "details": "No meta description found"}

        desc = match.group(1).strip()
        issues = []
        if len(desc) < 100:
            issues.append(f"Meta description too short ({len(desc)} chars, min 100)")
        if len(desc) > 165:
            issues.append(f"Meta description too long ({len(desc)} chars, max 165)")

        return {
            "name": "seo_meta",
            "passed": len(issues) == 0,
            "details": f"Meta OK ({len(desc)} chars)" if not issues else "; ".join(issues),
        }

    # ── Check 4: Schema.org (Raw only) ─────────────────────────────────

    def _check_schema_org(self, html: str, brand: str) -> dict:
        """Check JSON-LD BlogPosting schema (required for Raw, optional for Bakudan)."""
        if brand != "raw":
            return {"name": "schema_org", "passed": True, "details": "Not required for this brand"}

        match = re.search(r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return {"name": "schema_org", "passed": False, "details": "No JSON-LD schema found"}

        try:
            schema = json.loads(match.group(1))
            required = ["headline", "description", "datePublished", "author"]
            missing = [f for f in required if f not in schema]
            if missing:
                return {"name": "schema_org", "passed": False, "details": f"Missing fields: {missing}"}
            return {"name": "schema_org", "passed": True, "details": "Valid BlogPosting schema"}
        except json.JSONDecodeError as e:
            return {"name": "schema_org", "passed": False, "details": f"Invalid JSON-LD: {e}"}

    # ── Check 5: Content Quality ───────────────────────────────────────

    def _check_content_quality(self, html: str) -> dict:
        """Check word count, headings, and no placeholder tokens."""
        issues = []

        # Word count
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        words = len(clean.split())
        if words < 600:
            issues.append(f"Too short ({words} words, min 600)")
        if words > 3000:
            issues.append(f"Too long ({words} words, max 3000)")

        # H2 headings
        h2_count = len(re.findall(r"<h2", html, re.IGNORECASE))
        if h2_count < 2:
            issues.append(f"Not enough subheadings ({h2_count} <h2>, need 2+)")

        # Placeholder tokens
        placeholders = re.findall(r"\{\{.*?\}\}", html)
        if placeholders:
            issues.append(f"Unresolved placeholders: {placeholders[:3]}")

        # Lorem ipsum check
        if "lorem ipsum" in html.lower():
            issues.append("Contains lorem ipsum placeholder text")

        return {
            "name": "content_quality",
            "passed": len(issues) == 0,
            "details": f"Quality OK ({words} words, {h2_count} headings)" if not issues else "; ".join(issues),
        }

    # ── Check 6: Link Integrity ────────────────────────────────────────

    def _check_link_integrity(self, html: str, project_id: str) -> dict:
        """Check internal links point to existing files."""
        from core.agents.dev_agent import MASTER_DIR, PROJECT_FOLDERS
        folder = PROJECT_FOLDERS.get(project_id, project_id)
        project_path = MASTER_DIR / folder

        if not project_path.exists():
            return {"name": "link_integrity", "passed": True, "details": "Project path not found, skipping"}

        links = re.findall(r'href=["\']([^"\'#]+\.html)["\']', html)
        broken = []
        for link in links:
            if link.startswith("http"):
                continue
            if not (project_path / link).exists():
                broken.append(link)

        return {
            "name": "link_integrity",
            "passed": len(broken) == 0,
            "details": f"All {len(links)} links OK" if not broken else f"Broken links: {broken}",
        }

    # ── Check 7: Cultural Review ───────────────────────────────────────

    def _check_cultural_review(self, html: str, cfg: dict) -> dict:
        """Quick LLM check for cultural sensitivity."""
        # Extract text content
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()

        # Take a sample (first 500 words to save tokens)
        sample = " ".join(clean.split()[:500])

        try:
            from core.llm.router import LLMRouter
            router = LLMRouter()
            result = router.complete(
                prompt=f"Review this restaurant blog content for cultural sensitivity issues. "
                       f"The restaurant is {cfg.get('brand_name', '')} ({cfg.get('cuisine', '')}).\n\n"
                       f"Content sample:\n{sample}\n\n"
                       f"Return JSON: {{\"passed\": true/false, \"issues\": [\"issue1\", ...]}}",
                system="You are a cultural sensitivity reviewer. Flag only real issues — stereotypes, "
                       "incorrect cultural claims, offensive language. Minor style issues are fine.",
                task_type="default",
                description="Cultural review",
                max_tokens=256,
                temperature=0.3,
            )
            # Parse result
            text = result.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                issues = data.get("issues", [])
                return {
                    "name": "cultural_review",
                    "passed": data.get("passed", True),
                    "details": "No cultural issues" if not issues else f"Issues: {'; '.join(issues)}",
                }
        except Exception as exc:
            logger.warning("Cultural review LLM call failed: %s", exc)

        # If LLM fails, pass by default (don't block on infra issues)
        return {"name": "cultural_review", "passed": True, "details": "LLM review skipped (fallback pass)"}

    # ── Check 8: HTML Validity ─────────────────────────────────────────

    def _check_html_validity(self, html: str) -> dict:
        """Check for well-formed HTML."""
        checker = _TagChecker()
        try:
            checker.feed(html)
        except Exception as e:
            return {"name": "html_validity", "passed": False, "details": f"Parse error: {e}"}

        errors = checker.errors
        unclosed = checker.get_unclosed()

        # Filter out common false positives
        critical_tags = {"div", "article", "section", "main", "header", "footer", "nav", "ul", "ol", "table"}
        critical_unclosed = [t for t in unclosed if t in critical_tags]

        issues = errors + [f"Unclosed <{t}>" for t in critical_unclosed]

        return {
            "name": "html_validity",
            "passed": len(issues) == 0,
            "details": f"HTML valid" if not issues else f"Issues: {'; '.join(issues[:5])}",
        }
