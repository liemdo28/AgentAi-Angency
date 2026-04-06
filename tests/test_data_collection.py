"""
Stream D — Data Collection tests.

Covers:
  D1. Outbound email: send_data_request_email()
  D2. Inbound parse: parse_message(), extract_attachments_filenames()
  D3. Account mapping: map_email_to_account()
  D4. Save attachment: _save_attachment() path safety and file write
  D5. Trigger data task: process_inbound_email() task creation logic
"""
from __future__ import annotations

import email
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock, patch

import pytest

# ── Stub heavy deps not available in test environment ──────────────
# data_collection.py does local imports of these inside functions;
# stub them in sys.modules so those imports resolve to mocks.
import sys
from unittest.mock import MagicMock as _MagicMock
for _m in ["dotenv", "httpx", "anthropic", "openai"]:
    sys.modules.setdefault(_m, _MagicMock())

# Stub DB modules that are locally imported inside process_inbound_email
_mock_db_conn = _MagicMock()
_mock_task_repo_mod = _MagicMock()
sys.modules.setdefault("src.db.connection", _mock_db_conn)
sys.modules.setdefault("src.db.repositories.task_repo", _mock_task_repo_mod)

from src.ingestion.email_ingestion import (
    extract_attachments_filenames,
    map_email_to_account,
    parse_message,
)

for _cleanup in ["src.db.connection", "src.db.repositories.task_repo"]:
    sys.modules.pop(_cleanup, None)


# ------------------------------------------------------------------ #
# Fixture helpers                                                      #
# ------------------------------------------------------------------ #

def build_raw_email(
    from_addr: str = "sender@client.com",
    subject: str = "Monthly Report",
    body: str = "Please find attached.",
    attachments: list[tuple[str, bytes]] | None = None,
) -> bytes:
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg["To"] = "agency@agency.ai"
    msg.attach(MIMEText(body, "plain"))
    for name, content in (attachments or []):
        part = MIMEApplication(content, Name=name)
        part["Content-Disposition"] = f'attachment; filename="{name}"'
        msg.attach(part)
    return msg.as_bytes()


MAPPING = {"@client.com": "acct-001", "bob@brand.io": "acct-002"}


def make_mock_receipt(status="sent", error=None):
    from src.tools.email_client import EmailReceipt
    return EmailReceipt(
        message_id="msg-001",
        status=status,
        sent_at="2026-03-25T00:00:00+00:00",
        error=error,
    )


# ------------------------------------------------------------------ #
# D2. parse_message                                                    #
# ------------------------------------------------------------------ #

class TestParseMessage:
    def test_extracts_from_field(self):
        raw = build_raw_email(from_addr="alice@client.com")
        assert "alice@client.com" in parse_message(raw)["from"]

    def test_extracts_subject(self):
        raw = build_raw_email(subject="Q1 Data Report")
        assert parse_message(raw)["subject"] == "Q1 Data Report"

    def test_empty_bytes_returns_empty_headers(self):
        parsed = parse_message(b"")
        assert parsed["from"] == ""
        assert parsed["subject"] == ""

    def test_date_field_present(self):
        raw = build_raw_email()
        parsed = parse_message(raw)
        assert "date" in parsed

    def test_minimal_raw_email(self):
        raw = b"From: test@example.com\nSubject: Hello\n\nBody"
        parsed = parse_message(raw)
        assert "test@example.com" in parsed["from"]
        assert parsed["subject"] == "Hello"

    def test_multi_word_subject(self):
        raw = build_raw_email(subject="Q4 2025 Performance Review Data")
        assert parse_message(raw)["subject"] == "Q4 2025 Performance Review Data"


# ------------------------------------------------------------------ #
# D3. map_email_to_account                                             #
# ------------------------------------------------------------------ #

class TestMapEmailToAccount:
    def test_domain_match(self):
        assert map_email_to_account({"from": "alice@client.com"}, MAPPING) == "acct-001"

    def test_exact_email_match(self):
        assert map_email_to_account({"from": "bob@brand.io"}, MAPPING) == "acct-002"

    def test_case_insensitive(self):
        assert map_email_to_account({"from": "Alice@CLIENT.COM"}, MAPPING) == "acct-001"

    def test_no_match_returns_none(self):
        assert map_email_to_account({"from": "unknown@nowhere.com"}, MAPPING) is None

    def test_empty_mapping_returns_none(self):
        assert map_email_to_account({"from": "alice@client.com"}, {}) is None

    def test_empty_from_returns_none(self):
        assert map_email_to_account({"from": ""}, MAPPING) is None

    def test_missing_from_key_returns_none(self):
        assert map_email_to_account({}, MAPPING) is None

    def test_subdomain_still_matches(self):
        # "mail.client.com" contains "@client.com"? No — "@client.com" not in "sender@mail.client.com"
        # But "client.com" would match if that were the key
        mapping = {"client.com": "acct-001"}
        assert map_email_to_account({"from": "sender@mail.client.com"}, mapping) == "acct-001"


# ------------------------------------------------------------------ #
# D2. extract_attachments_filenames                                    #
# ------------------------------------------------------------------ #

class TestExtractAttachmentsFilenames:
    def test_no_attachments_returns_empty(self):
        raw = build_raw_email()
        msg = email.message_from_bytes(raw)
        assert list(extract_attachments_filenames(msg)) == []

    def test_single_attachment_filename(self):
        raw = build_raw_email(attachments=[("report.csv", b"col1,col2\n1,2")])
        msg = email.message_from_bytes(raw)
        filenames = list(extract_attachments_filenames(msg))
        assert "report.csv" in filenames

    def test_multiple_attachments(self):
        raw = build_raw_email(attachments=[("a.csv", b"data"), ("b.xlsx", b"data2")])
        msg = email.message_from_bytes(raw)
        filenames = list(extract_attachments_filenames(msg))
        assert "a.csv" in filenames
        assert "b.xlsx" in filenames

    def test_duplicate_filename_appears_twice(self):
        raw = build_raw_email(attachments=[("dup.csv", b"1"), ("dup.csv", b"2")])
        msg = email.message_from_bytes(raw)
        filenames = list(extract_attachments_filenames(msg))
        assert filenames.count("dup.csv") == 2


# ------------------------------------------------------------------ #
# D1. send_data_request_email                                          #
# ------------------------------------------------------------------ #

class TestSendDataRequestEmail:
    def _patched_send(self, receipt):
        mock_client = MagicMock()
        mock_client.send.return_value = receipt
        return patch("src.ingestion.data_collection._get_email_client", return_value=mock_client)

    def test_returns_sent_status(self):
        from src.ingestion.data_collection import send_data_request_email
        with self._patched_send(make_mock_receipt("sent")):
            result = send_data_request_email("acct-1", "client@example.com", "2026-03")
        assert result["status"] == "sent"

    def test_returns_account_id(self):
        from src.ingestion.data_collection import send_data_request_email
        with self._patched_send(make_mock_receipt()):
            result = send_data_request_email("acct-999", "x@y.com", "2026-03")
        assert result["account_id"] == "acct-999"

    def test_returns_report_date(self):
        from src.ingestion.data_collection import send_data_request_email
        with self._patched_send(make_mock_receipt()):
            result = send_data_request_email("acct-1", "x@y.com", "2026-03")
        assert result["report_date"] == "2026-03"

    def test_custom_subject_used(self):
        from src.ingestion.data_collection import send_data_request_email
        mock_client = MagicMock()
        mock_client.send.return_value = make_mock_receipt()
        with patch("src.ingestion.data_collection._get_email_client", return_value=mock_client):
            send_data_request_email("acct-1", "x@y.com", "2026-03", custom_subject="CUSTOM SUBJECT")
        sent_msg = mock_client.send.call_args[0][0]
        assert sent_msg.subject == "CUSTOM SUBJECT"

    def test_custom_body_used(self):
        from src.ingestion.data_collection import send_data_request_email
        mock_client = MagicMock()
        mock_client.send.return_value = make_mock_receipt()
        with patch("src.ingestion.data_collection._get_email_client", return_value=mock_client):
            send_data_request_email("acct-1", "x@y.com", "2026-03", custom_body="MY BODY TEXT")
        sent_msg = mock_client.send.call_args[0][0]
        assert sent_msg.body == "MY BODY TEXT"

    def test_smtp_fail_returns_failed(self):
        from src.ingestion.data_collection import send_data_request_email
        with self._patched_send(make_mock_receipt("failed", error="SMTP refused")):
            result = send_data_request_email("acct-1", "x@y.com", "2026-03")
        assert result["status"] == "failed"
        assert result["error"] == "SMTP refused"

    def test_default_subject_contains_report_date(self):
        from src.ingestion.data_collection import send_data_request_email
        mock_client = MagicMock()
        mock_client.send.return_value = make_mock_receipt()
        with patch("src.ingestion.data_collection._get_email_client", return_value=mock_client):
            send_data_request_email("acct-1", "x@y.com", "2026-03")
        sent_msg = mock_client.send.call_args[0][0]
        assert "2026-03" in sent_msg.subject

    def test_default_body_contains_account_id(self):
        from src.ingestion.data_collection import send_data_request_email
        mock_client = MagicMock()
        mock_client.send.return_value = make_mock_receipt()
        with patch("src.ingestion.data_collection._get_email_client", return_value=mock_client):
            send_data_request_email("acct-TESTID", "x@y.com", "2026-03")
        sent_msg = mock_client.send.call_args[0][0]
        assert "acct-TESTID" in sent_msg.body


# ------------------------------------------------------------------ #
# D4. _save_attachment                                                 #
# ------------------------------------------------------------------ #

class TestSaveAttachment:
    def _make_part(self, filename, payload):
        part = MagicMock()
        part.get_filename.return_value = filename
        part.get_payload.return_value = payload
        return part

    def test_normal_file_saved(self, tmp_path):
        from src.ingestion.data_collection import _save_attachment
        part = self._make_part("report.csv", b"a,b\n1,2")
        path = _save_attachment(part, str(tmp_path), "acct-1", "2026-03")
        assert os.path.exists(path)
        assert open(path, "rb").read() == b"a,b\n1,2"

    def test_path_traversal_stripped(self, tmp_path):
        from src.ingestion.data_collection import _save_attachment
        part = self._make_part("../../../etc/passwd", b"evil")
        path = _save_attachment(part, str(tmp_path), "acct-1", "2026-03")
        # Must land inside tmp_path, not escape it
        assert str(tmp_path) in path
        assert os.path.basename(path) == "passwd"

    def test_colons_in_date_replaced(self, tmp_path):
        from src.ingestion.data_collection import _save_attachment
        part = self._make_part("f.csv", b"x")
        path = _save_attachment(part, str(tmp_path), "acct-1", "2026:03:01 10:00")
        assert "2026-03-01_10-00" in path

    def test_no_filename_defaults_to_attachment(self, tmp_path):
        from src.ingestion.data_collection import _save_attachment
        part = self._make_part(None, b"data")
        path = _save_attachment(part, str(tmp_path), "acct-1", "2026-03")
        assert os.path.basename(path) == "attachment"

    def test_zero_byte_payload_no_file_written(self, tmp_path):
        from src.ingestion.data_collection import _save_attachment
        part = self._make_part("empty.csv", None)  # get_payload returns None
        path = _save_attachment(part, str(tmp_path), "acct-1", "2026-03")
        # Returns path but doesn't write (no payload)
        assert path.endswith("empty.csv")
        assert not os.path.exists(path)  # file not created for empty payload

    def test_dest_dir_created_automatically(self, tmp_path):
        from src.ingestion.data_collection import _save_attachment
        part = self._make_part("x.csv", b"data")
        path = _save_attachment(part, str(tmp_path), "new-account", "2026-04")
        assert os.path.isdir(os.path.dirname(path))


# ------------------------------------------------------------------ #
# D5. process_inbound_email                                            #
# ------------------------------------------------------------------ #

def _db_mocks(task_id: str = "task-xyz", create_error: Exception | None = None):
    """Return a patch.dict context that stubs the DB modules locally imported
    inside process_inbound_email."""
    mock_conn = MagicMock()
    mock_repo_mod = MagicMock()
    repo_instance = MagicMock()
    if create_error:
        repo_instance.create.side_effect = create_error
    else:
        created = MagicMock()
        created.id = task_id
        repo_instance.create.return_value = created
    mock_repo_mod.TaskRepository.return_value = repo_instance
    return patch.dict(sys.modules, {
        "src.db.connection": mock_conn,
        "src.db.repositories.task_repo": mock_repo_mod,
    }), repo_instance


class TestProcessInboundEmail:
    def test_unmatched_sender_returns_unmatched_status(self):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(from_addr="unknown@nowhere.net")
        result = process_inbound_email(raw, MAPPING)
        assert result["status"] == "unmatched"
        assert result["account_id"] is None
        assert result["task_id"] is None

    def test_no_attachment_returns_no_task(self):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(from_addr="alice@client.com")
        with patch("src.ingestion.data_collection._get_storage_dir", return_value="/tmp/test"):
            result = process_inbound_email(raw, MAPPING, trigger_task=True)
        assert result["task_id"] is None
        assert result["saved_files"] == []

    def test_attachment_file_saved(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(
            from_addr="alice@client.com",
            attachments=[("data.csv", b"header\nrow1")],
        )
        db_ctx, _ = _db_mocks()
        with (
            db_ctx,
            patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)),
        ):
            result = process_inbound_email(raw, MAPPING, trigger_task=False)

        assert len(result["saved_files"]) == 1
        assert result["saved_files"][0].endswith("data.csv")

    def test_trigger_false_no_task_created(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(
            from_addr="alice@client.com",
            attachments=[("report.csv", b"data")],
        )
        with patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)):
            result = process_inbound_email(raw, MAPPING, trigger_task=False)
        assert result["task_id"] is None

    def test_trigger_true_with_files_creates_task(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(
            from_addr="alice@client.com",
            attachments=[("report.csv", b"data")],
        )
        db_ctx, repo_instance = _db_mocks("task-xyz")
        with (
            db_ctx,
            patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)),
        ):
            result = process_inbound_email(raw, MAPPING, trigger_task=True)

        # task_id is the auto-generated UUID of the Task object, not the mock return value
        assert result["task_id"] is not None
        assert len(result["task_id"]) == 36  # UUID format
        assert repo_instance.create.called

    def test_task_create_failure_reported_in_errors(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(
            from_addr="alice@client.com",
            attachments=[("report.csv", b"data")],
        )
        db_ctx, _ = _db_mocks(create_error=Exception("DB write error"))
        with (
            db_ctx,
            patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)),
        ):
            result = process_inbound_email(raw, MAPPING, trigger_task=True)

        assert result["task_id"] is None
        assert any("Failed to create data task" in e for e in result["errors"])

    def test_status_partial_when_task_create_fails(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(
            from_addr="alice@client.com",
            attachments=[("report.csv", b"data")],
        )
        db_ctx, _ = _db_mocks(create_error=Exception("DB error"))
        with (
            db_ctx,
            patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)),
        ):
            result = process_inbound_email(raw, MAPPING, trigger_task=True)

        assert result["status"] == "partial"

    def test_multiple_attachments_all_saved(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(
            from_addr="alice@client.com",
            attachments=[("a.csv", b"data1"), ("b.xlsx", b"data2")],
        )
        db_ctx, _ = _db_mocks()
        with (
            db_ctx,
            patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)),
        ):
            result = process_inbound_email(raw, MAPPING, trigger_task=False)

        assert len(result["saved_files"]) == 2

    def test_account_id_in_result(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(from_addr="alice@client.com")
        with patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)):
            result = process_inbound_email(raw, MAPPING)
        assert result["account_id"] == "acct-001"

    def test_ok_status_when_no_errors(self, tmp_path):
        from src.ingestion.data_collection import process_inbound_email
        raw = build_raw_email(from_addr="alice@client.com")
        with patch("src.ingestion.data_collection._get_storage_dir", return_value=str(tmp_path)):
            result = process_inbound_email(raw, MAPPING, trigger_task=False)
        assert result["status"] == "ok"
        assert result["errors"] == []
