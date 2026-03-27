"""
Email notification node — sends results to stakeholders when task passes review.
Uses src.tools.EmailClient (SMTP + SendGrid).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.agents.state import AgenticState

logger = logging.getLogger(__name__)

# Default stakeholder email (override via metadata.stakeholder_email)
DEFAULT_STAKEHOLDER_EMAIL = "agency@example.com"


def send_notification(state: AgenticState) -> AgenticState:
    """
    Email notification node — dispatches results to the approver/stakeholder.

    Uses src.tools.EmailClient when configured; falls back to logging.
    """
    task_id = state.get("task_id", "?")
    to_dept = state.get("to_department", "?")
    policy = state.get("policy", {})
    outputs = state.get("generated_outputs", {})
    score = state.get("leader_score", 0)
    specialist_output = state.get("specialist_output", "")
    metadata = state.get("metadata", {})
    stakeholder_email = metadata.get("stakeholder_email", DEFAULT_STAKEHOLDER_EMAIL)

    subject = f"[Agency AI] Task Complete -- {to_dept} | Score: {score:.0f}/100 | {task_id}"

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
            body_lines.append(str(value)[:2000])
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

    # ── RISK-013: Approval gate — never auto-send without explicit approval ──
    require_approval = metadata.get("require_approval", True)
    human_approved = metadata.get("human_approved", False)

    if require_approval and not human_approved:
        logger.info(
            "[EMAIL] Notification HELD for task %s — require_approval=True, "
            "human_approved=False. Set metadata.human_approved=True to release.",
            task_id,
        )
        return {
            **state,
            "email_sent": False,
            "metadata": {
                **metadata,
                "notification_held": True,
                "notification_subject": subject,
                "notification_body": body,
                "notification_to": stakeholder_email,
            },
        }

    # Try real email send
    email_sent = _try_send_email(
        to=stakeholder_email,
        subject=subject,
        body=body,
        cc=metadata.get("cc_emails"),
    )

    return {
        **state,
        "email_sent": email_sent,
        "metadata": {
            **metadata,
            "notification_sent_to": stakeholder_email,
            "notification_subject": subject,
        },
    }


def _try_send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[list[str]] = None,
) -> bool:
    """Send email via EmailClient; log and return False on failure."""
    try:
        from src.tools.email_client import EmailClient, EmailMessage

        client = EmailClient()
        msg = EmailMessage(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
        )
        receipt = client.send(msg)
        client.close()

        if receipt.status == "sent":
            logger.info("[EMAIL] Sent to %s: %s", to, subject)
            return True
        else:
            logger.warning("[EMAIL] Failed to %s: %s -- %s", to, subject, receipt.error)
            return False
    except Exception as exc:
        logger.warning("[EMAIL] Could not send notification: %s", exc)
        return False
