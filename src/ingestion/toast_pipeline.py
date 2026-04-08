"""
toast_pipeline.py — End-to-end Toast report ingestion pipeline.

Orchestrates:
  1. Detect report type (filename + columns)
  2. Parse file (reuse file_parser)
  3. Map columns to canonical names
  4. Validate (toast_validators)
  5. Normalize (store/channel/item)
  6. SHA-256 dedup
  7. Insert into raw table
  8. Transform → normalized tables
  9. Update upload_files status

Entry points:
  - ingest_file(filepath) → IngestResult
  - ingest_directory(dirpath) → list[IngestResult]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.db.toast_schema import get_toast_db, init_toast_db
from src.ingestion.file_parser import parse_file, ParseResult
from src.ingestion.toast_normalizers import ToastRowNormalizer
from src.ingestion.toast_report_types import (
    REPORT_DEFINITIONS,
    ToastReportType,
    detect_report_type,
    get_definition,
    map_columns_to_canonical,
)
from src.ingestion.toast_validators import ValidationResult, validate

logger = logging.getLogger(__name__)


# ── Result Container ─────────────────────────────────────────────────────────

@dataclass
class IngestResult:
    """Result of ingesting a single Toast file."""
    file_path: str
    file_name: str
    report_type: ToastReportType
    status: str = "pending"  # pending, completed, failed, duplicate, unknown_type
    upload_file_id: str | None = None
    file_hash: str | None = None
    row_count: int = 0
    raw_rows_inserted: int = 0
    normalized_rows_inserted: int = 0
    validation: ValidationResult | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "report_type": self.report_type.value,
            "status": self.status,
            "upload_file_id": self.upload_file_id,
            "file_hash": self.file_hash,
            "row_count": self.row_count,
            "raw_rows_inserted": self.raw_rows_inserted,
            "normalized_rows_inserted": self.normalized_rows_inserted,
            "validation_errors": self.validation.error_count if self.validation else 0,
            "validation_warnings": self.validation.warning_count if self.validation else 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "duration_ms": self.duration_ms,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _compute_file_hash(filepath: str) -> str:
    """Compute SHA-256 hash of file contents."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _safe_int(val: Any) -> int:
    f = _safe_float(val)
    return int(round(f))


def _extract_date_range(rows: list[dict], date_field: str = "business_date") -> tuple[str, str]:
    """Extract min/max date from rows for a given date field."""
    dates = []
    for row in rows:
        d = row.get(date_field)
        if d and isinstance(d, str) and d.strip():
            dates.append(d.strip()[:10])  # Take YYYY-MM-DD part
    if not dates:
        return ("", "")
    dates.sort()
    return (dates[0], dates[-1])


# ── Pipeline Class ───────────────────────────────────────────────────────────

class ToastIngestPipeline:
    """
    Full Toast report ingestion pipeline.
    Handles detect → parse → map → validate → normalize → dedup → load.
    """

    def __init__(self, db: sqlite3.Connection | None = None):
        self._db = db or get_toast_db()
        self._normalizer = ToastRowNormalizer(self._db)

    def ingest_file(
        self,
        filepath: str,
        source: str = "manual",
        google_file_id: str | None = None,
        store_hint: str | None = None,
    ) -> IngestResult:
        """
        Ingest a single Toast report file.

        Parameters
        ----------
        filepath     : path to CSV/XLSX file
        source       : 'manual', 'gdrive', or 'api'
        google_file_id : Google Drive file ID if from Drive
        store_hint   : optional store_id hint from folder structure
        """
        start = datetime.now(timezone.utc)
        file_name = os.path.basename(filepath)
        result = IngestResult(file_path=filepath, file_name=file_name, report_type=ToastReportType.UNKNOWN)

        try:
            # 1. Compute file hash for dedup
            file_hash = _compute_file_hash(filepath)
            result.file_hash = file_hash
            file_size = os.path.getsize(filepath)

            # 2. Check if already processed
            existing = self._db.execute(
                "SELECT id, status FROM upload_files WHERE file_hash = ?", (file_hash,)
            ).fetchone()
            if existing:
                result.status = "duplicate"
                result.upload_file_id = existing["id"]
                result.errors.append(f"Duplicate file (hash matches upload {existing['id']}, status={existing['status']})")
                logger.info("Duplicate file skipped: %s (hash=%s)", file_name, file_hash[:12])
                return result

            # 3. Parse file
            parsed: ParseResult = parse_file(filepath)
            if not parsed.ok:
                result.status = "failed"
                result.errors.extend(parsed.errors)
                return result
            if not parsed.rows:
                result.status = "failed"
                result.errors.append("File parsed but contains no data rows")
                return result

            result.row_count = len(parsed.rows)

            # 4. Detect report type
            columns = list(parsed.rows[0].keys()) if parsed.rows else []
            report_type = detect_report_type(file_name, columns)
            result.report_type = report_type

            if report_type == ToastReportType.UNKNOWN:
                result.status = "unknown_type"
                result.errors.append(
                    f"Cannot detect report type from filename '{file_name}' or columns {columns[:10]}"
                )
                return result

            definition = get_definition(report_type)
            if not definition:
                result.status = "failed"
                result.errors.append(f"No definition found for report type: {report_type.value}")
                return result

            # 5. Map columns to canonical names
            col_mapping = map_columns_to_canonical(columns, report_type)
            mapped_rows = []
            for row in parsed.rows:
                mapped = {}
                for src_col, val in row.items():
                    canonical = col_mapping.get(src_col, src_col)
                    mapped[canonical] = val
                mapped_rows.append(mapped)

            # 6. Validate
            validation = validate(mapped_rows, report_type)
            result.validation = validation

            if not validation.is_valid:
                result.warnings.append(f"Validation has {validation.error_count} errors")
                # Continue anyway — we insert into raw and log errors

            # 7. Create upload_files record
            upload_id = f"uf_{uuid.uuid4().hex[:12]}"
            result.upload_file_id = upload_id
            date_start, date_end = _extract_date_range(mapped_rows)

            # Determine store_id from hint or first row
            store_id = store_hint
            if not store_id and mapped_rows:
                location = mapped_rows[0].get("location")
                store_id = self._normalizer.store.normalize(location)

            self._db.execute(
                """INSERT INTO upload_files
                   (id, google_file_id, file_name, report_type, store_id,
                    business_date_start, business_date_end, file_hash,
                    file_size_bytes, row_count, status, source,
                    error_count, warning_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing', ?, ?, ?)""",
                (upload_id, google_file_id, file_name, report_type.value,
                 store_id, date_start, date_end, file_hash,
                 file_size, len(mapped_rows), source,
                 validation.error_count, validation.warning_count),
            )
            self._db.commit()

            # 8. Insert into raw table
            raw_inserted = self._insert_raw(upload_id, definition.raw_table, mapped_rows, definition)
            result.raw_rows_inserted = raw_inserted

            # 9. Normalize and insert into normalized tables
            norm_inserted = self._normalize_and_insert(upload_id, report_type, mapped_rows, store_id)
            result.normalized_rows_inserted = norm_inserted

            # 10. Log validation issues
            self._log_validation_issues(upload_id, validation)

            # 11. Update upload_files status
            status = "completed" if validation.is_valid else "completed"
            self._db.execute(
                """UPDATE upload_files
                   SET status = ?, imported_at = ?, error_count = ?, warning_count = ?
                   WHERE id = ?""",
                (status, datetime.now(timezone.utc).isoformat(),
                 validation.error_count, validation.warning_count, upload_id),
            )
            self._db.commit()
            result.status = status

        except Exception as exc:
            result.status = "failed"
            result.errors.append(str(exc))
            logger.exception("Ingest failed for %s: %s", filepath, exc)

            # Update upload_files if record was created
            if result.upload_file_id:
                try:
                    self._db.execute(
                        "UPDATE upload_files SET status = 'failed', error_message = ? WHERE id = ?",
                        (str(exc), result.upload_file_id),
                    )
                    self._db.commit()
                except Exception:
                    pass

        finally:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            result.duration_ms = elapsed
            logger.info(
                "Ingest %s: %s — %d raw, %d norm, %.0fms",
                result.status, file_name, result.raw_rows_inserted,
                result.normalized_rows_inserted, elapsed,
            )

        return result

    def ingest_directory(
        self,
        dirpath: str,
        source: str = "manual",
        recursive: bool = False,
    ) -> list[IngestResult]:
        """Ingest all supported files in a directory."""
        results = []
        supported = {".csv", ".xlsx", ".xls", ".tsv"}
        dir_path = Path(dirpath)

        if not dir_path.exists():
            logger.error("Directory not found: %s", dirpath)
            return results

        pattern = "**/*" if recursive else "*"
        for f in sorted(dir_path.glob(pattern)):
            if f.is_file() and f.suffix.lower() in supported:
                result = self.ingest_file(str(f), source=source)
                results.append(result)

        logger.info(
            "Directory ingest complete: %d files, %d success, %d failed",
            len(results),
            sum(1 for r in results if r.status == "completed"),
            sum(1 for r in results if r.status == "failed"),
        )
        return results

    # ── Raw insertion ────────────────────────────────────────────────────

    def _insert_raw(
        self,
        upload_id: str,
        table_name: str,
        rows: list[dict[str, Any]],
        definition: Any,
    ) -> int:
        """Insert rows into the appropriate raw_* table."""
        if not rows:
            return 0

        # Get canonical column names that exist in the raw table
        canonical_cols = [f.canonical for f in definition.fields]
        inserted = 0

        for i, row in enumerate(rows):
            values = {col: str(row.get(col, "")) if row.get(col) is not None else None
                      for col in canonical_cols}
            values["upload_file_id"] = upload_id
            values["row_index"] = i
            values["raw_json"] = json.dumps({k: str(v) if v is not None else None for k, v in row.items()})

            cols = list(values.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_str = ", ".join(cols)

            try:
                self._db.execute(
                    f"INSERT OR IGNORE INTO {table_name} ({col_str}) VALUES ({placeholders})",
                    [values[c] for c in cols],
                )
                inserted += 1
            except sqlite3.OperationalError as e:
                # Table-missing or schema errors are fatal — re-raise
                raise sqlite3.OperationalError(
                    f"Raw insert into '{table_name}' failed at row {i}: {e}"
                ) from e
            except sqlite3.Error as e:
                logger.warning("Raw insert error at row %d: %s", i, e)

        self._db.commit()
        return inserted

    # ── Normalization + insertion ─────────────────────────────────────────

    def _normalize_and_insert(
        self,
        upload_id: str,
        report_type: ToastReportType,
        rows: list[dict[str, Any]],
        store_id_hint: str | None = None,
    ) -> int:
        """Normalize rows and insert into the appropriate normalized table."""
        handlers = {
            ToastReportType.ORDER_DETAILS: self._norm_orders,
            ToastReportType.PAYMENT_DETAILS: self._norm_payments,
            ToastReportType.ITEM_SELECTION: self._norm_items,
            ToastReportType.MODIFIER_SELECTION: self._norm_modifiers,
            ToastReportType.PRODUCT_MIX: self._norm_product_mix,
            ToastReportType.TIME_ENTRIES: self._norm_labor,
            ToastReportType.ACCOUNTING: self._norm_accounting,
            ToastReportType.MENU: self._norm_menu,
        }

        handler = handlers.get(report_type)
        if not handler:
            return 0

        count = 0
        for row in rows:
            norm_row = self._normalizer.normalize_row(dict(row))  # copy to avoid mutation
            sid = norm_row.get("store_id") or store_id_hint or ""
            norm_row["store_id"] = sid
            norm_row["upload_file_id"] = upload_id
            try:
                handler(norm_row)
                count += 1
            except sqlite3.IntegrityError:
                pass  # duplicate — skip
            except sqlite3.Error as e:
                logger.warning("Norm insert error: %s", e)

        self._db.commit()

        # Build aggregates for order-based reports
        if report_type == ToastReportType.ORDER_DETAILS:
            self._rebuild_daily_store_sales(upload_id)
            self._rebuild_daily_channel_sales(upload_id)
        elif report_type == ToastReportType.ITEM_SELECTION:
            self._rebuild_daily_item_sales(upload_id)

        return count

    def _norm_orders(self, row: dict) -> None:
        oid = row.get("order_id", "")
        sid = row.get("store_id", "")
        pk = f"{sid}_{oid}" if sid and oid else f"_{uuid.uuid4().hex[:8]}"

        self._db.execute(
            """INSERT OR REPLACE INTO orders
               (id, upload_file_id, store_id, location_raw, order_id, order_number,
                business_date, sent_date, closed_date, dining_option, channel,
                gross_sales, net_sales, tax, tips, discount_total,
                is_void, refund_amount, check_status, guest_count, server, revenue_center)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pk, row.get("upload_file_id"), sid, row.get("location_raw"),
             oid, row.get("order_number"),
             row.get("business_date"), row.get("sent_date"), row.get("closed_date"),
             row.get("dining_option"), row.get("channel"),
             _safe_float(row.get("gross_sales")), _safe_float(row.get("net_sales")),
             _safe_float(row.get("tax")), _safe_float(row.get("tips")),
             _safe_float(row.get("discount_total")),
             1 if str(row.get("void_status", "")).lower() in ("true", "yes", "1", "void", "voided") else 0,
             _safe_float(row.get("refund_amount")),
             row.get("check_status"), _safe_int(row.get("guest_count")) or None,
             row.get("server"), row.get("revenue_center")),
        )

    def _norm_payments(self, row: dict) -> None:
        self._db.execute(
            """INSERT OR IGNORE INTO payments
               (upload_file_id, store_id, order_id, order_number,
                payment_type, amount, tip, payment_status, card_type,
                close_date, business_date, refund_amount, is_void)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("upload_file_id"), row.get("store_id"),
             row.get("order_id"), row.get("order_number"),
             row.get("payment_type"), _safe_float(row.get("amount")),
             _safe_float(row.get("tip")), row.get("payment_status"),
             row.get("card_type"), row.get("close_date"),
             row.get("business_date"), _safe_float(row.get("refund_amount")),
             1 if str(row.get("void_status", "")).lower() in ("true", "yes", "1", "void") else 0),
        )

    def _norm_items(self, row: dict) -> None:
        self._db.execute(
            """INSERT INTO order_items
               (upload_file_id, store_id, order_id, order_number, sent_date,
                business_date, raw_item_name, item_name, sales_category, menu_group,
                qty, gross_amount, discount_amount, net_amount, tax, server, dining_option)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("upload_file_id"), row.get("store_id"),
             row.get("order_id"), row.get("order_number"),
             row.get("sent_date"), row.get("business_date"),
             row.get("raw_item_name", row.get("item_name")),
             row.get("item_name"),
             row.get("sales_category"), row.get("menu_group"),
             _safe_int(row.get("qty")) or 1,
             _safe_float(row.get("gross_amount")),
             _safe_float(row.get("discount_amount")),
             _safe_float(row.get("net_amount")),
             _safe_float(row.get("tax")),
             row.get("server"), row.get("dining_option")),
        )

    def _norm_modifiers(self, row: dict) -> None:
        self._db.execute(
            """INSERT INTO order_item_modifiers
               (upload_file_id, store_id, order_id, parent_item, modifier_name,
                qty, modifier_price, sent_date, business_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("upload_file_id"), row.get("store_id"),
             row.get("order_id"), row.get("parent_item"),
             row.get("modifier_name"), _safe_int(row.get("qty")) or 1,
             _safe_float(row.get("modifier_price")),
             row.get("sent_date"), row.get("business_date")),
        )

    def _norm_product_mix(self, row: dict) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO daily_item_sales
               (store_id, business_date, item_name, sales_category,
                qty_sold, gross_sales, net_sales, discount_total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("store_id"), row.get("business_date"),
             row.get("item_name"), row.get("category"),
             _safe_int(row.get("qty")),
             _safe_float(row.get("gross_sales")),
             _safe_float(row.get("net_sales")),
             _safe_float(row.get("discount"))),
        )

    def _norm_labor(self, row: dict) -> None:
        reg = _safe_float(row.get("regular_hours"))
        ot = _safe_float(row.get("overtime_hours"))
        self._db.execute(
            """INSERT OR REPLACE INTO labor_daily
               (store_id, business_date, employee, role,
                regular_hours, overtime_hours, total_hours,
                labor_cost, hourly_rate, tips)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("store_id"), row.get("business_date"),
             row.get("employee"), row.get("role"),
             reg, ot, reg + ot,
             _safe_float(row.get("labor_cost")),
             _safe_float(row.get("hourly_rate")),
             _safe_float(row.get("tips"))),
        )

    def _norm_accounting(self, row: dict) -> None:
        self._db.execute(
            """INSERT OR REPLACE INTO accounting_daily
               (store_id, business_date, account_code, account_name,
                revenue_bucket, tax_bucket, tender_bucket,
                amount, debit, credit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row.get("store_id"), row.get("business_date"),
             row.get("account_code"), row.get("account_name"),
             row.get("revenue_bucket"), row.get("tax_bucket"),
             row.get("tender_bucket"),
             _safe_float(row.get("amount")),
             _safe_float(row.get("debit")),
             _safe_float(row.get("credit"))),
        )

    def _norm_menu(self, row: dict) -> None:
        item_name = row.get("item_name", "")
        location = row.get("location", "")
        is_active = str(row.get("active", "")).lower()
        active = 0 if is_active in ("false", "no", "0", "archived", "inactive") else 1

        self._db.execute(
            """INSERT OR REPLACE INTO menu_items_master
               (item_id, raw_item_name, item_name, menu, category, subgroup,
                price, is_active, location, plu, description, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (row.get("item_id"), row.get("raw_item_name", item_name),
             item_name, row.get("menu"), row.get("category"),
             row.get("subgroup"), _safe_float(row.get("price")) or None,
             active, location, row.get("plu"), row.get("description")),
        )

    # ── Aggregate builders ───────────────────────────────────────────────

    def _rebuild_daily_store_sales(self, upload_id: str) -> None:
        """Build/update daily_store_sales from orders table for this upload."""
        self._db.execute("""
            INSERT OR REPLACE INTO daily_store_sales
                (store_id, business_date, order_count, gross_sales, net_sales,
                 tax_total, tips_total, discount_total, refund_total, void_count,
                 avg_order_value, guest_count)
            SELECT
                store_id, business_date,
                COUNT(*) as order_count,
                COALESCE(SUM(gross_sales), 0),
                COALESCE(SUM(net_sales), 0),
                COALESCE(SUM(tax), 0),
                COALESCE(SUM(tips), 0),
                COALESCE(SUM(discount_total), 0),
                COALESCE(SUM(refund_amount), 0),
                COALESCE(SUM(is_void), 0),
                CASE WHEN COUNT(*) > 0 THEN COALESCE(SUM(net_sales), 0) / COUNT(*) ELSE 0 END,
                COALESCE(SUM(guest_count), 0)
            FROM orders
            WHERE upload_file_id = ?
            GROUP BY store_id, business_date
        """, (upload_id,))
        self._db.commit()

    def _rebuild_daily_channel_sales(self, upload_id: str) -> None:
        """Build/update daily_channel_sales from orders table."""
        self._db.execute("""
            INSERT OR REPLACE INTO daily_channel_sales
                (store_id, business_date, channel, order_count, gross_sales, net_sales)
            SELECT
                store_id, business_date, COALESCE(channel, 'other'),
                COUNT(*),
                COALESCE(SUM(gross_sales), 0),
                COALESCE(SUM(net_sales), 0)
            FROM orders
            WHERE upload_file_id = ?
            GROUP BY store_id, business_date, channel
        """, (upload_id,))
        self._db.commit()

    def _rebuild_daily_item_sales(self, upload_id: str) -> None:
        """Build/update daily_item_sales from order_items table."""
        self._db.execute("""
            INSERT OR REPLACE INTO daily_item_sales
                (store_id, business_date, item_name, sales_category,
                 qty_sold, gross_sales, net_sales, discount_total)
            SELECT
                store_id, business_date, item_name, sales_category,
                COALESCE(SUM(qty), 0),
                COALESCE(SUM(gross_amount), 0),
                COALESCE(SUM(net_amount), 0),
                COALESCE(SUM(discount_amount), 0)
            FROM order_items
            WHERE upload_file_id = ?
            GROUP BY store_id, business_date, item_name
        """, (upload_id,))
        self._db.commit()

    # ── Validation issue logging ─────────────────────────────────────────

    def _log_validation_issues(self, upload_id: str, validation: ValidationResult) -> None:
        """Log validation issues to toast_ingest_errors table."""
        for issue in validation.issues:
            self._db.execute(
                """INSERT INTO toast_ingest_errors
                   (upload_file_id, error_code, severity, row_index, column_name, message, raw_value)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (upload_id, issue.code, issue.severity, issue.row_index,
                 issue.column, issue.message, issue.raw_value),
            )
        self._db.commit()

    # ── Query helpers ────────────────────────────────────────────────────

    def get_upload_status(self, limit: int = 50) -> list[dict]:
        """Get recent upload file statuses."""
        rows = self._db.execute(
            """SELECT id, file_name, report_type, store_id, status,
                      row_count, error_count, warning_count, uploaded_at, imported_at
               FROM upload_files
               ORDER BY uploaded_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_ingest_errors(self, upload_id: str | None = None, limit: int = 100) -> list[dict]:
        """Get ingest errors, optionally filtered by upload_id."""
        if upload_id:
            rows = self._db.execute(
                "SELECT * FROM toast_ingest_errors WHERE upload_file_id = ? ORDER BY created_at DESC LIMIT ?",
                (upload_id, limit),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM toast_ingest_errors ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
