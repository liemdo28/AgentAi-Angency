"""
Integration tests for data ingestion — file parsing, email processing, KPI extraction.
"""
import csv
import email
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


# ── File Parser: CSV ─────────────────────────────────────────────────────────

class TestCSVParser:
    def _write_csv(self, rows: list[dict], tmpdir: str) -> str:
        filepath = os.path.join(tmpdir, "report.csv")
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return filepath

    def test_parse_basic_csv(self):
        from src.ingestion.file_parser import parse_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = self._write_csv([
                {"Campaign": "FB Ads", "Impressions": "100000", "Clicks": "2500", "Spend": "500000"},
                {"Campaign": "Google", "Impressions": "80000", "Clicks": "3200", "Spend": "400000"},
            ], tmpdir)
            result = parse_csv(filepath)
            assert result.ok
            assert result.row_count == 2
            assert result.file_type == "csv"
            assert "campaign" in result.rows[0]
            assert result.rows[0]["impressions"] == 100000

    def test_parse_csv_with_commas_in_values(self):
        from src.ingestion.file_parser import parse_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "data.csv")
            with open(filepath, "w") as f:
                f.write("Metric,Value\n")
                f.write("Revenue,\"1,500,000\"\n")
                f.write("Spend,\"800,000\"\n")
            result = parse_csv(filepath)
            assert result.ok
            assert result.row_count == 2
            # Value should be coerced to number (commas stripped)
            assert result.rows[0]["value"] == 1500000

    def test_parse_empty_csv(self):
        from src.ingestion.file_parser import parse_csv

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "empty.csv")
            with open(filepath, "w") as f:
                f.write("Col1,Col2\n")
            result = parse_csv(filepath)
            assert result.ok
            assert result.row_count == 0

    def test_parse_nonexistent_file(self):
        from src.ingestion.file_parser import parse_csv
        result = parse_csv("/nonexistent/path.csv")
        assert not result.ok
        assert len(result.errors) > 0


# ── File Parser: Auto-detect ─────────────────────────────────────────────────

class TestFileParserAutoDetect:
    def test_auto_detect_csv(self):
        from src.ingestion.file_parser import parse_file

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "data.csv")
            with open(filepath, "w") as f:
                f.write("Name,Value\nTest,123\n")
            result = parse_file(filepath)
            assert result.ok
            assert result.file_type == "csv"

    def test_unsupported_extension(self):
        from src.ingestion.file_parser import parse_file

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "data.docx")
            with open(filepath, "w") as f:
                f.write("content")
            result = parse_file(filepath)
            assert not result.ok
            assert "Unsupported" in result.errors[0]

    def test_parse_multiple_files(self):
        from src.ingestion.file_parser import parse_files

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = os.path.join(tmpdir, "a.csv")
            f2 = os.path.join(tmpdir, "b.csv")
            for fp in [f1, f2]:
                with open(fp, "w") as f:
                    f.write("Col,Val\nA,1\n")
            results = parse_files([f1, f2])
            assert len(results) == 2
            assert all(r.ok for r in results)


# ── KPI Extraction ───────────────────────────────────────────────────────────

class TestKPIExtraction:
    def test_extract_kpis_from_campaign_data(self):
        from src.ingestion.file_parser import extract_kpis_from_rows

        rows = [
            {"impressions": 100000, "clicks": 2500, "spend": 500000, "conversions": 150, "revenue": 2000000},
            {"impressions": 80000, "clicks": 3200, "spend": 400000, "conversions": 200, "revenue": 2500000},
        ]
        kpis = extract_kpis_from_rows(rows)
        assert kpis["impressions"] == 180000
        assert kpis["clicks"] == 5700
        assert kpis["spend"] == 900000
        assert kpis["conversions"] == 350
        assert kpis["revenue"] == 4500000
        # Derived metrics
        assert "ctr" in kpis
        assert "cpc" in kpis
        assert "cpa" in kpis
        assert "roas" in kpis
        assert kpis["roas"] == 5.0  # 4500000 / 900000

    def test_extract_kpis_empty_rows(self):
        from src.ingestion.file_parser import extract_kpis_from_rows
        kpis = extract_kpis_from_rows([])
        assert kpis == {}

    def test_extract_kpis_no_matching_columns(self):
        from src.ingestion.file_parser import extract_kpis_from_rows
        rows = [{"name": "Test", "color": "blue"}]
        kpis = extract_kpis_from_rows(rows)
        assert kpis == {}

    def test_extract_kpis_string_numbers(self):
        """Values like '1,500,000' should be parsed correctly."""
        from src.ingestion.file_parser import extract_kpis_from_rows

        rows = [
            {"impressions": "1,500,000", "clicks": "25,000", "spend": "5,000,000"},
        ]
        kpis = extract_kpis_from_rows(rows)
        assert kpis["impressions"] == 1500000
        assert kpis["clicks"] == 25000


# ── Email Ingestion ──────────────────────────────────────────────────────────

class TestEmailIngestion:
    def test_parse_message(self):
        from src.ingestion.email_ingestion import parse_message

        raw = (
            b"From: bob@acme.com\r\n"
            b"Subject: Monthly Report\r\n"
            b"Date: Wed, 26 Mar 2026 10:00:00 +0000\r\n"
            b"\r\n"
            b"Please find attached the report.\r\n"
        )
        parsed = parse_message(raw)
        assert parsed["from"] == "bob@acme.com"
        assert parsed["subject"] == "Monthly Report"

    def test_map_email_to_account(self):
        from src.ingestion.email_ingestion import map_email_to_account

        parsed = {"from": "alice@brand.io"}
        mapping = {"@brand.io": "acct-001", "@acme.com": "acct-002"}
        assert map_email_to_account(parsed, mapping) == "acct-001"

    def test_map_email_no_match(self):
        from src.ingestion.email_ingestion import map_email_to_account

        parsed = {"from": "unknown@random.org"}
        mapping = {"@brand.io": "acct-001"}
        assert map_email_to_account(parsed, mapping) is None

    def test_extract_attachment_filenames(self):
        from src.ingestion.email_ingestion import extract_attachments_filenames

        msg = email.message.EmailMessage()
        msg["From"] = "test@test.com"
        msg["Subject"] = "Report"
        msg.set_content("Body text")
        msg.add_attachment(b"csv data", maintype="text", subtype="csv", filename="report.csv")

        filenames = list(extract_attachments_filenames(msg))
        assert "report.csv" in filenames


# ── Data Collection Pipeline (integration) ───────────────────────────────────

def _can_import_data_collection():
    try:
        from src.ingestion.data_collection import process_inbound_email
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _can_import_data_collection(), reason="Missing deps (httpx, etc.)")
class TestDataCollectionPipeline:
    def _build_email_with_csv(self, sender: str, csv_content: bytes) -> bytes:
        """Build a raw RFC-822 email with a CSV attachment."""
        msg = email.message.EmailMessage()
        msg["From"] = sender
        msg["Subject"] = "Monthly Performance Report"
        msg["Date"] = "Wed, 26 Mar 2026 10:00:00 +0000"
        msg.set_content("Hi, please find attached our monthly report.")
        msg.add_attachment(
            csv_content,
            maintype="text",
            subtype="csv",
            filename="performance.csv",
        )
        return msg.as_bytes()

    def test_process_inbound_email_saves_files(self):
        from src.ingestion.data_collection import process_inbound_email

        csv_data = b"Campaign,Impressions,Clicks,Spend\nFB,100000,2500,500000\n"
        raw_email = self._build_email_with_csv("bob@acme.com", csv_data)
        mapping = {"@acme.com": "acct-001"}

        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["LOCAL_STORAGE_PATH"] = tmpdir
            result = process_inbound_email(
                raw_bytes=raw_email,
                account_mapping=mapping,
                trigger_task=False,  # Don't trigger DB task in unit test
            )
            del os.environ["LOCAL_STORAGE_PATH"]

        assert result["account_id"] == "acct-001"
        assert len(result["saved_files"]) >= 1
        assert result["status"] in ("ok", "partial")
        # Check that parsed KPIs were extracted
        assert "parsed_kpis" in result

    def test_process_inbound_email_unmatched_sender(self):
        from src.ingestion.data_collection import process_inbound_email

        raw_email = self._build_email_with_csv("unknown@random.org", b"data")
        mapping = {"@acme.com": "acct-001"}

        result = process_inbound_email(
            raw_bytes=raw_email,
            account_mapping=mapping,
            trigger_task=False,
        )
        assert result["status"] == "unmatched"
        assert result["account_id"] is None


# ── ParseResult ──────────────────────────────────────────────────────────────

class TestParseResult:
    def test_to_dict(self):
        from src.ingestion.file_parser import ParseResult

        pr = ParseResult(
            filename="test.csv",
            file_type="csv",
            rows=[{"a": 1}, {"a": 2}],
        )
        d = pr.to_dict()
        assert d["row_count"] == 2
        assert d["filename"] == "test.csv"

    def test_summary(self):
        from src.ingestion.file_parser import ParseResult

        pr = ParseResult(
            filename="report.csv",
            file_type="csv",
            rows=[{"impressions": 100, "clicks": 10}],
        )
        s = pr.summary()
        assert "report.csv" in s
        assert "1 rows" in s
