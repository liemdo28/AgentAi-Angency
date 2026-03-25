"""
Email notification node — sends results to stakeholders when task passes review.
Currently a mock (logs); full SMTP/SendGrid in Layer 4.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgenticState

logger = logging.getLogger(__name__)


def send_notification(state: AgenticState) -> AgenticState:
    """
    Email notification node — dispatches results to the approver/stakeholder.

    Currently a mock: logs the email content.
    Full implementation in Layer 4 (SMTP/SendGrid).
    """
    task_id = state.get("task_id", "?")
    to_dept = state.get("to_department", "?")
    policy = state.get("policy", {})
    outputs = state.get("generated_outputs", {})
    score = state.get("leader_score", 0)
    specialist_output = state.get("specialist_output", "")

    subject = f"[Agency AI] Task Complete — {to_dept} | Score: {score:.0f}/100 | {task_id}"

    # Build email body
    body_lines = [
        f"Task ID: {task_id}",
        f"Department: {to_dept}",
        f"Status: PASSED (score {score:.0f}/100)",
        f"Expected outputs: {', '.join(policy.get('expected_outputs', []))}",
        "",
        "--- GENERATED OUTPUTS ---",
        "",
    ]

    if isinstance(outputs, dict):
        for key, value in outputs.items():
            body_lines.append(f"### {key}")
            body_lines.append(str(value)[:2000])  # truncate per section
            body_lines.append("")

    body_lines.extend([
        "",
        "--- FULL SPECIALIST OUTPUT ---",
        specialist_output[:3000],
        "",
        "---",
        "This is an automated message from the Agency AI system.",
        "Review in the Agency dashboard.",
    ])

    body = "\n".join(body_lines)

    # Mock send — log it
    logger.info(f"[EMAIL MOCK] To: {policy.get('approver_role', 'Unknown')}")
    logger.info(f"[EMAIL MOCK] Subject: {subject}")
    logger.info(f"[EMAIL MOCK] Body:\n{body[:500]}...")

    # TODO (Layer 4): implement real email via SMTP or SendGrid
    # from src.config import SETTINGS
    # if SETTINGS.SENDGRID_API_KEY:
    #     _send_via_sendgrid(subject, body, SETTINGS.EMAIL_FROM)
    # elif SETTINGS.SMTP_HOST:
    #     _send_via_smtp(subject, body, SETTINGS.SMTP_HOST, ...)

    return {
        **state,
        "email_sent": True,
        "metadata": {
            **state.get("metadata", {}),
            "notification_sent_to": policy.get("approver_role"),
            "notification_subject": subject,
        },
    }
