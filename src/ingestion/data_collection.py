"""
data_collection.py — End-to-end email data collection workflow.

Two entry points:
  1. send_data_request_email()  — agency → client: request a periodic report
  2. process_inbound_email()    — client → agency: parse reply, extract
                                  attachments, store files, trigger Data AI task

This module wires together EmailClient, email_ingestion, FileStorage,
TaskRepository, and task_runner.
"""
from __future__ import annotations

import email
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from src.ingestion.email_ingestion import (
    extract_attachments_filenames,
    map_email_to_account,
    parse_message,
)
from src.tasks.models import Priority, Task, TaskStatus, now_iso
from src.tools.email_client import EmailClient, EmailMessage

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_email_client() -> EmailClient:
    return EmailClient()


def _get_storage_dir() -> str:
    path = os.getenv("LOCAL_STORAGE_PATH", "./storage/attachments")
    os.makedirs(path, exist_ok=True)
    return path


def _save_attachment(
    part: Any, storage_dir: str, account_id: str, report_date: str
) -> str:
    """Save a MIME attachment to local storage; return file path."""
    filename = part.get_filename() or "attachment"
    safe_date = report_date.replace(":", "-").replace(" ", "_")
    dest_dir = os.path.join(storage_dir, account_id, safe_date)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    payload = part.get_payload(decode=True)
    if payload:
        with open(dest, "wb") as f:
            f.write(payload)
        logger.info("Saved attachment %s -> %s", filename, dest)
    return dest


# ── Outbound: request report from client ──────────────────────────────────────

def send_data_request_email(
    account_id: str,
    account_email: str,
    report_date: str,
    custom_subject: Optional[str] = None,
    custom_body: Optional[str] = None,
) -> dict[str, Any]:
    """
    Send a scheduled data-request email to a client.

    Parameters
    ----------
    account_id    : internal account identifier (for tracking)
    account_email : client's email address
    report_date   : reporting period label, e.g. "2026-03"
    custom_subject: override the default subject line
    custom_body   : override the default message body

    Returns a dict with keys: status, message_id, error
    """
    subject = custom_subject or (
        f"[AI Agency] Monthly Data Report Request — {report_date}"
    )
    body = custom_body or (
        f"Dear Client,\n\n"
        f"We kindly request your monthly performance report for the period: {report_date}.\n\n"
        f"Please reply to this email with the following attachments:\n"
        f"  • Campaign performance data (CSV or Excel)\n"
        f"  • Ad spend summary\n"
        f"  • Any other relevant KPI reports\n\n"
        f"Account reference: {account_id}\n\n"
        f"Thank you,\nAI Agency Team"
    )

    client = _get_email_client()
    receipt = client.send(
        EmailMessage(to=account_email, subject=subject, body=body)
    )

    result = {
        "account_id": account_id,
        "account_email": account_email,
        "report_date": report_date,
        "status": receipt.status,
        "message_id": receipt.message_id,
        "sent_at": receipt.sent_at,
        "error": receipt.error,
    }
    if receipt.status == "sent":
        logger.info(
            "Data request email sent for account=%s period=%s", account_id, report_date
        )
    else:
        logger.warning(
            "Data request email FAILED for account=%s: %s", account_id, receipt.error
        )
    return result


# ── Inbound: process client reply with attachments ────────────────────────────

def process_inbound_email(
    raw_bytes: bytes,
    account_mapping: dict[str, str],
    trigger_task: bool = True,
) -> dict[str, Any]:
    """
    Parse an inbound email reply, extract and store attachments, and
    optionally trigger a Data-department AI task to process the files.

    Parameters
    ----------
    raw_bytes       : raw RFC-822 bytes of the received email
    account_mapping : dict mapping partial sender email/domain → account_id,
                      e.g. {"@acme.com": "acct-001", "bob@brand.io": "acct-002"}
    trigger_task    : if True, create and enqueue a Data AI task for the files

    Returns a dict with keys:
      account_id, saved_files, task_id (if triggered), status, errors
    """
    errors: list[str] = []
    saved_files: list[str] = []
    task_id: Optional[str] = None

    # ── 1. Parse headers ──────────────────────────────────────────────
    parsed = parse_message(raw_bytes)
    sender = parsed.get("from", "")
    subject = parsed.get("subject", "")
    report_date = datetime.now(timezone.utc).strftime("%Y-%m")

    # ── 2. Resolve account ────────────────────────────────────────────
    account_id = map_email_to_account(parsed, account_mapping)
    if not account_id:
        msg = f"No account mapping found for sender: {sender}"
        logger.warning(msg)
        errors.append(msg)
        return {
            "account_id": None,
            "saved_files": [],
            "task_id": None,
            "status": "unmatched",
            "errors": errors,
        }

    # ── 3. Parse full MIME message to access parts ────────────────────
    msg_obj = email.message_from_bytes(raw_bytes)
    storage_dir = _get_storage_dir()

    for part in msg_obj.walk():
        filename = part.get_filename()
        if not filename:
            continue
        try:
            path = _save_attachment(part, storage_dir, account_id, report_date)
            saved_files.append(path)
        except Exception as exc:
            err = f"Failed to save attachment {filename}: {exc}"
            logger.error(err)
            errors.append(err)

    if not saved_files:
        logger.info("Inbound email from %s had no attachments.", sender)

    # ── 4. Trigger Data AI task ───────────────────────────────────────
    if trigger_task and saved_files:
        try:
            from src.db.connection import init_db
            from src.db.repositories.task_repo import TaskRepository
            from src.tasks.models import Task

            init_db()
            repo = TaskRepository()
            task = Task(
                account_id=account_id,
                goal="Process inbound client data report",
                description=(
                    f"Sender: {sender}\n"
                    f"Subject: {subject}\n"
                    f"Report period: {report_date}\n"
                    f"Attachments saved:\n" + "\n".join(f"  - {f}" for f in saved_files)
                ),
                task_type="data_ingestion",
                current_department="data",
                priority=Priority.HIGH,
                kpis={},
                status=TaskStatus.PENDING,
                created_at=now_iso(),
            )
            repo.create(task)
            task_id = task.id
            logger.info(
                "Created data ingestion task %s for account %s (%d files)",
                task_id, account_id, len(saved_files),
            )
        except Exception as exc:
            err = f"Failed to create data task: {exc}"
            logger.error(err)
            errors.append(err)

    return {
        "account_id": account_id,
        "saved_files": saved_files,
        "task_id": task_id,
        "status": "ok" if not errors else "partial",
        "errors": errors,
    }
