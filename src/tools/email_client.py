"""
Email Client — SMTP + SendGrid driver for outbound notifications.
Also supports IMAP polling for inbound email ingestion.
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str | list[str]
    subject: str
    body: str
    html_body: Optional[str] = None
    from_addr: Optional[str] = None
    cc: Optional[list[str]] = None
    bcc: Optional[list[str]] = None
    attachments: Optional[list[tuple[str, bytes]]] = None  # (filename, content)


@dataclass
class EmailReceipt:
    message_id: str
    status: str  # "sent" | "queued" | "failed"
    sent_at: str
    error: Optional[str] = None


class EmailClient:
    """
    Send transactional and campaign emails via SMTP or SendGrid API.

    Priority order:
    1. SendGrid API (if SENDGRID_API_KEY set)
    2. SMTP (if SMTP_HOST set)

    Also supports IMAP for reading inbound emails (inbound ingestion pipeline).
    """

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_tls: bool = True,
        sendgrid_key: Optional[str] = None,
        default_from: Optional[str] = None,
    ) -> None:
        self._smtp_host = smtp_host or os.getenv("SMTP_HOST")
        self._smtp_port = int(os.getenv("SMTP_PORT", smtp_port))
        self._smtp_user = smtp_user or os.getenv("SMTP_USER")
        self._smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self._smtp_tls = smtp_tls
        self._sendgrid_key = sendgrid_key or os.getenv("SENDGRID_API_KEY")
        self._default_from = default_from or os.getenv("EMAIL_FROM", "agency@agency.ai")
        self._http = httpx.Client(timeout=30.0)

    # ── Send ───────────────────────────────────────────────────────────

    def send(self, msg: EmailMessage) -> EmailReceipt:
        """Send an email. Returns a receipt with status."""
        to_list = [msg.to] if isinstance(msg.to, str) else msg.to
        msg.from_addr = msg.from_addr or self._default_from

        if self._sendgrid_key:
            return self._send_via_sendgrid(msg, to_list)
        elif self._smtp_host:
            return self._send_via_smtp(msg, to_list)
        else:
            logger.warning("No email driver configured. Email not sent.")
            return EmailReceipt(
                message_id="",
                status="failed",
                sent_at=datetime.now(timezone.utc).isoformat(),
                error="No SMTP_HOST or SENDGRID_API_KEY configured",
            )

    def _send_via_sendgrid(self, msg: EmailMessage, to_list: list[str]) -> EmailReceipt:
        """Send via SendGrid REST API."""
        try:
            payload: dict[str, Any] = {
                "personalizations": [
                    {
                        "to": [{"email": addr} for addr in to_list],
                        "subject": msg.subject,
                    }
                ],
                "from": {"email": msg.from_addr},
                "content": [],
            }
            if msg.body:
                payload["content"].append({"type": "text/plain", "value": msg.body})
            if msg.html_body:
                payload["content"].append({"type": "text/html", "value": msg.html_body})
            if msg.cc:
                payload["personalizations"][0]["cc"] = [
                    {"email": addr} for addr in msg.cc
                ]

            r = self._http.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._sendgrid_key}",
                    "Content-Type": "application/json",
                },
            )
            if r.status_code in (200, 201, 202):
                msg_id = r.headers.get("X-Message-Id", "sendgrid")
                return EmailReceipt(
                    message_id=msg_id,
                    status="sent",
                    sent_at=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return EmailReceipt(
                    message_id="",
                    status="failed",
                    sent_at=datetime.now(timezone.utc).isoformat(),
                    error=f"SendGrid {r.status_code}: {r.text[:200]}",
                )
        except Exception as exc:
            logger.error("SendGrid send failed: %s", exc)
            return EmailReceipt(
                message_id="",
                status="failed",
                sent_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )

    def _send_via_smtp(self, msg: EmailMessage, to_list: list[str]) -> EmailReceipt:
        """Send via SMTP."""
        try:
            mime = MIMEMultipart("alternative")
            mime["Subject"] = msg.subject
            mime["From"] = msg.from_addr
            mime["To"] = ", ".join(to_list)
            if msg.cc:
                mime["Cc"] = ", ".join(msg.cc)
            mime.attach(MIMEText(msg.body, "plain"))
            if msg.html_body:
                mime.attach(MIMEText(msg.html_body, "html"))

            # SMTP connection
            context = ssl.create_default_context()
            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                if self._smtp_tls:
                    server.starttls(context=context)
                if self._smtp_user and self._smtp_password:
                    server.login(self._smtp_user, self._smtp_password)
                all_recipients = to_list + (msg.cc or []) + (msg.bcc or [])
                server.sendmail(msg.from_addr, all_recipients, mime.as_string())

            return EmailReceipt(
                message_id="smtp",
                status="sent",
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.error("SMTP send failed: %s", exc)
            return EmailReceipt(
                message_id="",
                status="failed",
                sent_at=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )

    # ── Convenience methods ────────────────────────────────────────────

    def send_task_notification(
        self,
        to: str,
        task_id: str,
        task_name: str,
        status: str,
        score: float,
        campaign_id: Optional[str] = None,
    ) -> EmailReceipt:
        """Send a task status notification email."""
        subject = f"[AI Agency] Task {status.upper()}: {task_name}"
        body = (
            f"Task Update\n"
            f"==========\n"
            f"Task: {task_name}\n"
            f"ID: {task_id}\n"
            f"Status: {status}\n"
            f"Score: {score:.1f}/100\n"
            f"Campaign: {campaign_id or 'N/A'}\n\n"
            f"View details in the AI Agency dashboard.\n"
        )
        html = f"""
        <html><body>
        <h2>Task Update</h2>
        <table>
        <tr><td><b>Task</b></td><td>{task_name}</td></tr>
        <tr><td><b>ID</b></td><td>{task_id}</td></tr>
        <tr><td><b>Status</b></td><td>{status.upper()}</td></tr>
        <tr><td><b>Score</b></td><td>{score:.1f}/100</td></tr>
        <tr><td><b>Campaign</b></td><td>{campaign_id or 'N/A'}</td></tr>
        </table>
        </body></html>
        """
        return self.send(EmailMessage(to=to, subject=subject, body=body, html_body=html))

    def send_escalation_alert(
        self,
        to: str,
        task_id: str,
        reason: str,
        escalation_type: str,
    ) -> EmailReceipt:
        """Send a human escalation alert email."""
        subject = f"[ESCALATION] AI Agency requires human review: {task_id}"
        body = (
            f"ESCALATION ALERT\n"
            f"=================\n"
            f"Task: {task_id}\n"
            f"Type: {escalation_type}\n"
            f"Reason: {reason}\n\n"
            f"Please log in to the AI Agency dashboard to review and take action.\n"
        )
        html = f"""
        <html><body>
        <h2 style="color:red">ESCALATION ALERT</h2>
        <p><b>Task:</b> {task_id}</p>
        <p><b>Type:</b> {escalation_type}</p>
        <p><b>Reason:</b> {reason}</p>
        <p>Please review in the AI Agency dashboard.</p>
        </body></html>
        """
        return self.send(EmailMessage(to=to, subject=subject, body=body, html_body=html))

    # ── IMAP (inbound) ─────────────────────────────────────────────────

    def fetch_inbox(
        self,
        host: str,
        user: str,
        password: str,
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Fetch emails from an IMAP mailbox (for inbound ingestion pipeline).

        Requires imapclient package.

        Returns list of dicts: {subject, from_addr, date, body, message_id}
        """
        try:
            import imaplib
            from email import parser as email_parser
        except ImportError:
            logger.warning("imapclient not installed. IMAP fetch skipped.")
            return []

        try:
            with imaplib.IMAP4_SSL(host) as server:
                server.login(user, password)
                server.select(folder)

                search_criteria = "UNSEEN" if unread_only else "ALL"
                status, message_ids = server.search(None, search_criteria)
                ids = message_ids[0].split()[-limit:]

                emails = []
                for mid in ids:
                    status, msg_data = server.fetch(mid, "(RFC822)")
                    if msg_data and msg_data[0]:
                        raw = msg_data[0][1]
                        parser = email_parser.BytesParser()
                        msg = parser.parsebytes(raw)
                        emails.append({
                            "message_id": msg.get("Message-ID", ""),
                            "subject": msg.get("Subject", ""),
                            "from": msg.get("From", ""),
                            "date": msg.get("Date", ""),
                            "body": msg.get_body("plain") or "",
                        })
                return emails
        except Exception as exc:
            logger.error("IMAP fetch failed: %s", exc)
            return []

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "EmailClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
