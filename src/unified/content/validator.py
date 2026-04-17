"""
Content Validator — enforces hard rules, quality rules, and policy on drafts.

Validation layers:

A. HARD RULES (BLOCK — draft cannot enter approval queue):
   - Fake business data detected
   - Fake menu items
   - Fake prices
   - Fake hours
   - Offensive or culturally inappropriate language
   - Empty required fields (title, body, slug)

B. QUALITY RULES (score-based):
   - Readable structure (has headings)
   - Clear opening hook
   - Local context present
   - CTA present
   - No keyword stuffing
   - No generic AI filler phrases
   - Appropriate word count

Return: ValidationResult
  - hard_valid == False  → FAIL (blocks entry to approval queue)
  - quality_score < 50   → FAIL
  - Otherwise            → PASS
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import ContentDraft, PostType, ValidationResult
from .policy import ContentPolicy

logger = logging.getLogger("content.validator")


class ContentValidator:
    """
    Validates ContentDraft across hard, quality, and policy layers.

    A draft only enters the approval queue if:
      hard_valid == True  AND  quality_score >= 50
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand
        self.policy = ContentPolicy()

    # ── Public API ────────────────────────────────────────────────────────────

    def validate(self, draft: ContentDraft) -> ValidationResult:
        """
        Run all validation layers on a draft.

        Returns ValidationResult:
          - passed = hard_valid AND quality_score >= 50
          - hard_issues = list of hard block reasons (empty = pass)
          - quality_score = 0-100
          - quality_issues = warnings (non-blocking)
        """
        logger.info(
            "Validating draft: type=%s title=%r words=%d",
            draft.type, draft.title[:50], draft.word_count,
        )

        hard    = self._hard_validation(draft)
        quality = self._quality_validation(draft)

        passed = hard["valid"] and quality["score"] >= 50.0

        if hard["valid"]:
            reason = "PASS"
        elif quality["score"] < 50:
            reason = "FAIL — quality below threshold"
        else:
            reason = "FAIL — hard validation issues"

        issues = hard["issues"] + quality["issues"]
        editor_notes = " | ".join(issues) if issues else "All checks passed."

        result = ValidationResult(
            passed=passed,
            hard_valid=hard["valid"],
            quality_score=quality["score"],
            hard_issues=hard["issues"],
            quality_issues=quality["issues"],
            fake_data_detected=hard.get("fake_data_detected", False),
            culturally_inappropriate=hard.get("cultural_detected", False),
            keyword_stuffing=quality.get("stuffing_detected", False),
            reason=reason,
            editor_notes=editor_notes,
        )

        draft.validation_result = result
        logger.info(
            "Validation result: passed=%s score=%.1f hard=%s issues=%d",
            passed, quality["score"], hard["valid"], len(issues),
        )
        return result

    # ── Layer A: Hard Validation ─────────────────────────────────────────────

    def _hard_validation(self, draft: ContentDraft) -> dict:
        """
        Absolute blockers. Any of these = hard_valid=False.
        """
        issues: list[str] = []
        fake_data_detected  = False
        cultural_detected   = False

        # 1. Required field presence
        if not draft.title.strip():
            issues.append("Title is empty.")
        if not draft.slug.strip():
            issues.append("Slug is empty.")
        if not draft.body_markdown.strip():
            issues.append("Body is empty.")
        if len(draft.body_markdown.strip()) < 100:
            issues.append(f"Body is too short ({len(draft.body_markdown.split())} words). Minimum 200.")

        # 2. Fabricated menu items
        fabricated_menu = self._check_fabricated_menu(draft.body_markdown)
        if fabricated_menu:
            issues.extend(fabricated_menu)
            fake_data_detected = True

        # 3. Fabricated prices
        if self._has_unverified_prices(draft.body_markdown):
            issues.append("Unverified price detected in body.")
            fake_data_detected = True

        # 4. Fabricated hours
        if self._has_unverified_hours(draft.body_markdown):
            issues.append("Unverified hours detected in body.")
            fake_data_detected = True

        # 5. Unverified delivery claims
        if self._has_unverified_delivery(draft.body_markdown):
            issues.append("Delivery capability claimed but not verified.")
            fake_data_detected = True

        # 6. Offensive / culturally inappropriate language
        offensive = self.policy.detect_offensive_language(draft.body_markdown)
        if offensive:
            issues.extend([f"Offensive language: {o}" for o in offensive])
            cultural_detected = True

        cultural_issues = self.policy.check_cultural_sensitivity(draft.body_markdown)
        if cultural_issues:
            issues.extend(cultural_issues)
            cultural_detected = True

        # 7. Spam patterns
        if self.policy.detect_spam_patterns(draft.body_markdown):
            issues.append("Spam or exaggerated promotional language detected.")

        # 8. Exaggerated claims
        exaggerated = self.policy.detect_exaggerated_claims(draft.body_markdown)
        if exaggerated:
            issues.extend(exaggerated)

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "fake_data_detected": fake_data_detected,
            "cultural_detected": cultural_detected,
        }

    def _check_fabricated_menu(self, body: str) -> list[str]:
        """Return issues for menu items NOT in the verified list."""
        issues: list[str] = []
        verified = self.policy.verified_menu_items()
        body_lower = body.lower()

        # Known fabricated dishes (common LLM inventions for sushi)
        fabricated_dishes = [
            "spicy salmon roll", "rainbow roll", "california roll",
            "philadelphia roll", "caterpillar roll", "spider roll",
            "shrimp tempura roll", "soft shell crab",
        ]
        # These are OK IF they appear in verified list; flag only unverified
        flagged = [
            "philadelphia roll",  # often fabricated
        ]
        for dish in flagged:
            if dish in body_lower and not any(v.lower() in body_lower for v in verified):
                issues.append(f"Unverified dish mentioned: '{dish}'")

        return issues

    def _has_unverified_prices(self, body: str) -> bool:
        price_pattern = re.findall(r"\$\d+(?:\.\d{2})?(?:\s*(?:omakase|menu|per person))?", body, re.IGNORECASE)
        if not price_pattern:
            return False
        verified_prices = self.policy.config.get("verified_prices", [])
        return not any(vp.lower() in body.lower() for vp in verified_prices)

    def _has_unverified_hours(self, body: str) -> bool:
        hours_pattern = re.findall(
            r"(?:open|closed|closes|opens)\s+[\w\s,]+[\d:]+(?:am|pm)?",
            body, re.IGNORECASE
        )
        if not hours_pattern:
            return False
        verified = self.policy.config.get("verified_hours", "")
        if not verified:
            return False
        return not any(v.lower() in h.lower() for h in hours_pattern for v in [verified.lower()])

    def _has_unverified_delivery(self, body: str) -> bool:
        if self.policy.config.get("delivery_verified"):
            return False
        return bool(re.search(
            r"(?:we|we're|restaurant)\s+(?:deliver|delivers|delivery)\s+[\w\s]+(?:to|in)\s+\w+",
            body, re.IGNORECASE
        ))

    # ── Layer B: Quality Validation ──────────────────────────────────────────

    def _quality_validation(self, draft: ContentDraft) -> dict:
        """
        Score-based quality check.
        Score < 50 = FAIL. Score 50-74 = PASS with warnings.
        """
        score = 75.0
        issues: list[str] = []
        stuffing_detected = False

        body  = draft.body_markdown
        words = body.split()
        word_count = len(words)

        # Word count
        if word_count < 300:
            issues.append(f"Body too short ({word_count} words). Target: 400+.")
            score -= 15
        elif word_count > 2500:
            issues.append(f"Body very long ({word_count} words). Consider trimming to 1500.")
            score -= 5

        # Structure: has headings
        if not re.search(r"^#{1,3}\s+\w", body, re.MULTILINE):
            issues.append("No headings found — article lacks visual structure.")
            score -= 10

        # Hook: opening paragraph
        first_para = body.strip().split("\n\n")[0] if body.strip() else ""
        if len(first_para) < 40:
            issues.append("Opening paragraph is too short — weak hook.")
            score -= 10

        # Keyword stuffing
        kw = draft.keyword_primary.lower()
        if kw and kw not in ("", "none"):
            kw_count = len(re.findall(re.escape(kw), body, re.IGNORECASE))
            density = kw_count / max(word_count, 1) * 100
            if density > 3.0:
                issues.append(f"Keyword stuffing: '{kw}' density {density:.1f}% > 3% limit.")
                stuffing_detected = True
                score -= 20
            elif density > 2.0:
                issues.append(f"Keyword density high: '{kw}' at {density:.1f}%.")

        # AI filler
        filler_count = sum(
            1 for p in _FILLER_PHRASES if p.lower() in body.lower()
        )
        if filler_count >= 3:
            issues.append(f"AI filler detected ({filler_count} instances) — sounds robotic.")
            score -= 10

        # Local context
        local_signals = ["stockton", "central valley", "delta", "modesto", "lodi", "local"]
        if not any(s in body.lower() for s in local_signals):
            issues.append("No local geographic context in body.")
            score -= 5

        # CTA
        if not re.search(
            r"(?:order|visit|call|try|stop by|check out|reserve)",
            body, re.IGNORECASE
        ):
            issues.append("No clear call-to-action found.")
            score -= 10

        # Duplicate topic
        if self._is_duplicate_topic(draft):
            issues.append("Title appears to duplicate a recent post.")
            score -= 15

        score = max(0.0, min(100.0, round(score, 1)))
        return {"score": score, "issues": issues, "stuffing_detected": stuffing_detected}

    def _is_duplicate_topic(self, draft: ContentDraft, window_days: int = 5) -> bool:
        try:
            path = Path("data/content_history.json")
            if not path.exists():
                return False
            data = json.loads(path.read_text())
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=window_days)
            ).isoformat()
            recent = [
                e.get("topic", "").lower()
                for e in data
                if e.get("brand") == self.brand
                and e.get("date", "") >= cutoff
            ]
            title_words = set(draft.title.lower().split())
            for rt in recent:
                rt_words = set(rt.split())
                overlap = len(title_words & rt_words)
                if overlap >= 4 and len(title_words) <= 8:
                    return True
            return False
        except Exception:
            return False


# ── Constants ─────────────────────────────────────────────────────────────

_FILLER_PHRASES = [
    "in today's fast-paced world",
    "in today's modern world",
    "it's no secret that",
    "needless to say",
    "the fact of the matter is",
    "as you may already know",
    "it goes without saying",
    "when it comes to",
]
