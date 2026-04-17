"""
Content Validator — enforces hard, quality, and policy rules on generated drafts.

Three validation layers:
  A. Hard Validation — blocks publish if any of these fail:
       - No fabricated business facts
       - No fabricated menu items or prices
       - No fabricated hours
       - No offensive or culturally inappropriate language
  B. Quality Validation — scoring + warnings:
       - Readable structure (headings, paragraphs)
       - Clear hook
       - Local context present
       - Proper CTA
       - No keyword stuffing
       - No robotic AI filler
       - Not a duplicate of recent posts
  C. Policy Validation — brand + cultural tone:
       - Matches restaurant tone
       - Respectful language
       - No exaggerated claims or spam

Any hard validation failure → publish_decision = FAIL (blocks approval).
Quality warnings are surfaced to reviewer but do not block.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .models import ContentDraft, RiskLevel, ValidationResult
from .policy import ContentPolicy

logger = logging.getLogger("content_automation.validator")


# ─────────────────────────────────────────────────────────────────────────────
#  ContentValidator
# ─────────────────────────────────────────────────────────────────────────────

class ContentValidator:
    """
    Validates a ContentDraft across three enforcement layers.

    Returns a ValidationResult with passed/fail, risk level, and detailed issue lists.
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand
        self.policy = ContentPolicy()

    # ── Public API ────────────────────────────────────────────────────────────

    def validate(self, draft: ContentDraft) -> ValidationResult:
        """
        Run all three validation layers on a draft.

        Returns ValidationResult where:
          - passed=True only if ALL of: hard_valid, quality_score>=50, policy_passed
          - risk_level reflects the most severe issue found
        """
        logger.info(
            "Validating draft: plan_id=%s type=%s title=%r",
            draft.plan_id, draft.post_type, draft.title[:60],
        )

        hard_result    = self._hard_validation(draft)
        quality_result = self._quality_validation(draft)
        policy_result  = self._policy_validation(draft)

        # Determine overall pass
        passed = (
            hard_result["valid"]
            and quality_result["score"] >= 50.0
            and policy_result["passed"]
        )

        # Determine risk level
        risk = RiskLevel.LOW
        if hard_result["valid"] is False:
            risk = RiskLevel.HIGH
        elif policy_result["issues"]:
            risk = RiskLevel.MEDIUM

        # Decision
        if not hard_result["valid"]:
            decision = "FAIL"
        elif quality_result["score"] < 50:
            decision = "FAIL"
        elif not policy_result["passed"]:
            decision = "REVIEW"
        elif quality_result["score"] < 75:
            decision = "REVIEW"
        else:
            decision = "PASS"

        result = ValidationResult(
            passed=passed,
            risk_level=risk,
            hard_valid=hard_result["valid"],
            hard_issues=hard_result["issues"],
            quality_score=quality_result["score"],
            quality_issues=quality_result["issues"],
            policy_passed=policy_result["passed"],
            policy_issues=policy_result["issues"],
            publish_decision=decision,
            editor_notes=self._build_editor_notes(hard_result, quality_result, policy_result),
            fabricated_data_detected=bool(hard_result["fabricated_detected"]),
            culturally_inappropriate_detected=bool(policy_result["cultural_flag"]),
            keyword_stuffing_detected=bool(quality_result["stuffing_detected"]),
            duplicate_topic_detected=bool(quality_result["duplicate_detected"]),
        )

        draft.validation_result = result
        logger.info(
            "Validation complete: decision=%s risk=%s hard=%s quality=%.1f policy=%s",
            decision, risk.value, hard_result["valid"],
            quality_result["score"], policy_result["passed"],
        )
        return result

    # ── Layer A: Hard Validation ──────────────────────────────────────────────

    def _hard_validation(self, draft: ContentDraft) -> dict:
        """
        Absolute blockers. If ANY of these are true, the draft CANNOT be published.
        """
        issues: list[str] = []
        fabricated_detected = False

        body = draft.body_markdown.lower()
        title = draft.title.lower()

        # 1. Fabricated business facts
        fabricated = self._check_fabricated_facts(draft)
        if fabricated:
            issues.extend(fabricated)
            fabricated_detected = True

        # 2. Fabricated prices (e.g., "$12.99 omakase" when not verified)
        price_pattern = re.findall(r"\$\d+(?:\.\d{2})?(?:\s*/|\s+for\s+)", body)
        if price_pattern:
            verified_prices = self.policy.config.get("verified_prices", [])
            for price in price_pattern:
                if not any(vp in body for vp in verified_prices):
                    issues.append(f"Potentially unverified price found: '{price}'")

        # 3. Fabricated hours (must match verified hours)
        hours_pattern = re.findall(
            r"(?:open|closed|hours?|closes?|opens?)\s+[\w\s,]+[\d:ap\.m]+",
            body, re.IGNORECASE
        )
        if hours_pattern:
            verified_hours = self.policy.config.get("verified_hours", "")
            if verified_hours and not any(vh.lower() in h.lower() for h in hours_pattern for vh in [verified_hours.lower()]):
                issues.append("Hours mentioned may not match verified hours.")

        # 4. Fabricated delivery claims (only if NOT verified)
        delivery_claims = re.findall(r"(?:deliver|delivery)\s+[\w\s]+(?:to|in)\s+[\w\s]+", body)
        if delivery_claims:
            if not self.policy.config.get("delivery_verified"):
                issues.append(
                    "Delivery capability claimed but not confirmed in verified data."
                )

        # 5. Offensive / culturally inappropriate language
        offensive = self.policy.detect_offensive_language(draft.body_markdown)
        if offensive:
            issues.extend([f"Offensive language: {o}" for o in offensive])
            fabricated_detected = True

        # 6. Empty required fields
        if not draft.title.strip():
            issues.append("Title is empty.")
        if not draft.body_markdown.strip():
            issues.append("Body is empty.")
        if not draft.cta_text.strip():
            issues.append("CTA text is missing.")
        if not draft.slug.strip():
            issues.append("Slug is missing.")

        return {"valid": len(issues) == 0, "issues": issues, "fabricated_detected": fabricated_detected}

    def _check_fabricated_facts(self, draft: ContentDraft) -> list[str]:
        """
        Check for invented facts using the policy's known_facts system.
        """
        issues = []
        body = draft.body_markdown
        verified_business_data = self._get_verified_text()

        # Pattern: claims about awards, rankings, certifications not in verified data
        fabricated_claims = re.findall(
            r"(?:award|voted|best|top|#1|ranked|\\#1|certified|imported from)\s+[\w\s\-',]+",
            body, re.IGNORECASE
        )
        if fabricated_claims:
            # Simple heuristic: if it's an extraordinary claim without context
            for claim in fabricated_claims:
                if len(claim) > 10 and not any(
                    v.lower() in claim.lower() for v in ["stockton", "central valley", "raw sushi bar"]
                ):
                    issues.append(f"Unverified claim: '{claim.strip()}'")

        # Check: mentions other locations not in verified store list
        all_addresses = self.policy.config.get("known_addresses", [])
        if all_addresses:
            for addr_mention in re.finditer(r"\d+\s+[\w\s]+(?:st|ave|rd|blvd|pkwy|dr)", body, re.IGNORECASE):
                addr = addr_mention.group()
                if not any(addr.lower() in va.lower() for va in all_addresses):
                    issues.append(f"Address mentioned that is not in verified locations: '{addr}'")

        return issues

    # ── Layer B: Quality Validation ──────────────────────────────────────────

    def _quality_validation(self, draft: ContentDraft) -> dict:
        """
        Score-based quality check. Score < 50 = hard fail. Score < 75 = review flag.
        """
        score = 70.0
        issues: list[str] = []
        stuffing_detected = False
        duplicate_detected = False

        body = draft.body_markdown
        words = body.split()

        # Structure checks
        if not re.search(r"^#{1,3}\s+\w", body, re.MULTILINE):
            issues.append("No headings found — article may lack structure.")
            score -= 10
        if len(words) < 200:
            issues.append(f"Body is very short ({len(words)} words). Target: 400+.")
            score -= 15
        elif len(words) > 3000:
            issues.append(f"Body is very long ({len(words)} words). Consider trimming.")
            score -= 5

        # Hook check
        first_para = body.strip().split("\n\n")[0] if body.strip() else ""
        if len(first_para) < 50:
            issues.append("Opening paragraph is too short — weak hook.")
            score -= 10

        # Keyword stuffing
        kw = draft.focus_keyword.lower()
        if kw and kw not in ["", "none"]:
            kw_count = len(re.findall(re.escape(kw), body, re.IGNORECASE))
            kw_density = kw_count / max(len(words), 1) * 100
            if kw_density > 3.0:
                issues.append(f"Keyword stuffing detected: '{kw}' density {kw_density:.1f}%")
                stuffing_detected = True
                score -= 20
            elif kw_density > 2.0:
                issues.append(f"Keyword density high: '{kw}' at {kw_density:.1f}%.")
                score -= 5

        # AI filler detection
        filler_phrases = [
            "in today's fast-paced world",
            "in today's modern world",
            "it's no secret that",
            "needless to say",
            "the fact of the matter is",
            "as you may already know",
            "it goes without saying",
        ]
        filler_count = sum(1 for p in filler_phrases if p in body.lower())
        if filler_count >= 3:
            issues.append(f"Robotic AI filler detected ({filler_count} instances).")
            score -= 10

        # Duplicate check (simple title word overlap with recent)
        if self._is_duplicate_title(draft.title):
            issues.append("Title appears to duplicate a recent post.")
            duplicate_detected = True
            score -= 15

        # Local context present
        local_signals = ["stockton", "central valley", "delta", "modesto", "lodi", "local"]
        local_found = sum(1 for s in local_signals if s in body.lower())
        if local_found == 0:
            issues.append("No local geographic context found in body.")
            score -= 5

        # CTA present
        cta_patterns = [r"order", r"visit", r"call", r"reserv", r"stop by", r"try today"]
        if not any(re.search(p, body, re.IGNORECASE) for p in cta_patterns):
            issues.append("No clear call-to-action found in body.")
            score -= 10

        score = max(0.0, min(100.0, score))
        return {
            "score": round(score, 1),
            "issues": issues,
            "stuffing_detected": stuffing_detected,
            "duplicate_detected": duplicate_detected,
        }

    # ── Layer C: Policy Validation ───────────────────────────────────────────

    def _policy_validation(self, draft: ContentDraft) -> dict:
        """
        Brand tone, cultural sensitivity, and content policy check.
        """
        issues: list[str] = []
        cultural_flag = False

        # Brand tone check (only if configured)
        brand_tone_rules = self.policy.config.get("brand_tone_rules", {})
        if brand_tone_rules:
            tone_violations = self.policy.check_brand_tone(
                draft.body_markdown, brand_tone_rules
            )
            if tone_violations:
                issues.extend(tone_violations)

        # Cultural sensitivity
        cultural = self.policy.check_cultural_sensitivity(draft.body_markdown)
        if cultural:
            issues.extend(cultural)
            cultural_flag = True

        # Exaggerated claims
        exaggerated = self._check_exaggerated_claims(draft.body_markdown)
        if exaggerated:
            issues.extend(exaggerated)

        # Spam patterns
        if self.policy.detect_spam_patterns(draft.body_markdown):
            issues.append("Spam patterns detected — sounds promotional rather than helpful.")

        return {"passed": len(issues) == 0, "issues": issues, "cultural_flag": cultural_flag}

    def _check_exaggerated_claims(self, body: str) -> list[str]:
        issues = []
        exaggerated = [
            (r"best\s+(?:sushi|restaurant|food)\s+(?:in|ever|you'll ever)", "Avoid 'best ever' superlatives without qualification."),
            (r"the\s+only\s+place\s+to\s+\w+", "Avoid 'the only place' — too absolute."),
            (r"guaranteed\s+\w+", "Avoid guaranteed outcomes."),
            (r"you\s+will\s+never\s+\w+", "Avoid absolute negative promises."),
        ]
        for pattern, msg in exaggerated:
            if re.search(pattern, body, re.IGNORECASE):
                issues.append(f"Exaggerated claim: {msg}")
        return issues

    def _is_duplicate_title(self, title: str, lookback_days: int = 5) -> bool:
        """Check if title is too similar to recently published posts."""
        try:
            from pathlib import Path
            import json
            from datetime import datetime, timedelta, timezone

            history_path = Path("data/content_automation_history.json")
            if not history_path.exists():
                return False

            data = json.loads(history_path.read_text())
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=lookback_days)
            ).isoformat()

            recent_titles = [
                e["title"].lower() for e in data
                if e.get("date", "") >= cutoff
                and e.get("title")
            ]

            title_words = set(title.lower().split())
            for rt in recent_titles:
                rt_words = set(rt.split())
                overlap = len(title_words & rt_words)
                if overlap >= 4 and len(title_words) <= 8:
                    return True
            return False
        except Exception:
            return False

    def _get_verified_text(self) -> str:
        try:
            from core.content.store_data import get_verified_business_data
            return get_verified_business_data(self.brand)
        except Exception:
            return ""

    @staticmethod
    def _build_editor_notes(
        hard: dict, quality: dict, policy: dict
    ) -> str:
        parts = []
        if hard["issues"]:
            parts.append(f"[HARD FAIL] {'; '.join(hard['issues'])}")
        if quality["issues"]:
            parts.append(f"[QUALITY] {'; '.join(quality['issues'])}")
        if policy["issues"]:
            parts.append(f"[POLICY] {'; '.join(policy['issues'])}")
        if not parts:
            parts.append("No issues found.")
        return " | ".join(parts)
