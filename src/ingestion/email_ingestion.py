from __future__ import annotations

import email
from email.message import Message
from typing import Iterable


def parse_message(raw_bytes: bytes) -> dict[str, str]:
    msg: Message = email.message_from_bytes(raw_bytes)
    return {
        "from": msg.get("From", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
    }


def map_email_to_account(parsed: dict[str, str], account_mapping: dict[str, str]) -> str | None:
    sender = parsed.get("from", "").lower()
    for key, account in account_mapping.items():
        if key.lower() in sender:
            return account
    return None


def extract_attachments_filenames(message: Message) -> Iterable[str]:
    for part in message.walk():
        filename = part.get_filename()
        if filename:
            yield filename
