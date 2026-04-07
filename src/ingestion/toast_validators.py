"""
toast_validators.py — Validation rules for each Toast report type.

Validates:
  - Required column presence
  - Data type correctness (numeric, date, non-null)
  - Duplicate detection (order_id, etc.)
  - Business rule checks (negative amounts, future dates, etc.)

Returns ValidationResult with structured errors and warnings.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.ingestion.toast_report_types import (
    REPORT_DEFINITIONS,
    ToastReportType,
)

logger = logging.getLogger(__name__)


# ── Error Codes ──────────────────────────────────────────────────────────────

class ErrorCode:
    MISSING_REQUIRED_COLUMN = "MISSING_REQUIRED_COLUMN"
    NULL_REQUIRED_FIELD = "NULL_REQUIRED_FIELD"
    INVALID_NUMERIC = "INVALID_NUMERIC"
    INVALID_DATE = "INVALID_DATE"
    INVALID_INTEGER = "INVALID_INTEGER"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    DUPLICATE_ROW = "DUPLICATE_ROW"
    UNKNOWN_STORE = "UNKNOWN_STORE"
    FUTURE_DATE = "FUTURE_DATE"
    EMPTY_FILE = "EMPTY_FILE"
    UNSUPPORTED_TEMPLATE = "UNSUPPORTED_TEMPLATE"


# ── Result Containers ────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    """A single validation error or warning."""
    code: str
    severity: str  # "error" or "warning"
    row_index: int | None = None
    column: str | None = None
    message: str = ""
    raw_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "row_index": self.row_index,
            "column": self.column,
            "message": self.message,
            "raw_value": self.raw_value,
        }


@dataclass
class ValidationResult:
    """Result of validating a parsed Toast report."""
    report_type: ToastReportType
    row_count: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def add_error(self, code: str, message: str, row_index: int | None = None,
                  column: str | None = None, raw_value: str | None = None) -> None:
        self.issues.append(ValidationIssue(
            code=code, severity="error", row_index=row_index,
            column=column, message=message, raw_value=raw_value,
        ))

    def add_warning(self, code: str, message: str, row_index: int | None = None,
                    column: str | None = None, raw_value: str | None = None) -> None:
        self.issues.append(ValidationIssue(
            code=code, severity="warning", row_index=row_index,
            column=column, message=message, raw_value=raw_value,
        ))

    def summary(self) -> str:
        return (
            f"Validation: {self.row_count} rows, "
            f"{self.error_count} errors, {self.warning_count} warnings"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_type": self.report_type.value,
            "row_count": self.row_count,
            "is_valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    r"\d{4}-\d{2}-\d{2}",       # 2026-04-01
    r"\d{2}/\d{2}/\d{4}",       # 04/01/2026
    r"\d{1,2}/\d{1,2}/\d{4}",   # 4/1/2026
]


def _is_numeric(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return True
    if isinstance(val, str):
        cleaned = val.strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
        try:
            float(cleaned)
            return True
        except ValueError:
            return False
    return False


def _to_float_safe(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _is_date_like(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    return any(re.match(p, s) for p in _DATE_PATTERNS)


def _is_null_or_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    return False


# ── Main Validator ───────────────────────────────────────────────────────────

def validate_toast_report(
    rows: list[dict[str, Any]],
    report_type: ToastReportType,
    column_mapping: dict[str, str] | None = None,
) -> ValidationResult:
    """
    Validate parsed rows for a specific Toast report type.

    Parameters
    ----------
    rows : list of dicts with canonical field names as keys
    report_type : which Toast report this is
    column_mapping : optional {source_col: canonical_col} used during parsing

    Returns
    -------
    ValidationResult with errors and warnings
    """
    result = ValidationResult(report_type=report_type, row_count=len(rows))
    definition = REPORT_DEFINITIONS.get(report_type)

    if not definition:
        result.add_error(ErrorCode.UNSUPPORTED_TEMPLATE, f"No definition for report type: {report_type.value}")
        return result

    if not rows:
        result.add_error(ErrorCode.EMPTY_FILE, "File contains no data rows")
        return result

    # 1. Check required columns exist in first row
    sample_keys = set(rows[0].keys())
    for req_col in definition.required_columns:
        if req_col not in sample_keys:
            result.add_error(
                ErrorCode.MISSING_REQUIRED_COLUMN,
                f"Required column '{req_col}' not found. Available: {sorted(sample_keys)}",
                column=req_col,
            )

    if result.error_count > 0:
        return result  # Stop early if required columns missing

    # 2. Build field type map
    field_types: dict[str, str] = {}
    field_required: set[str] = set()
    for fspec in definition.fields:
        field_types[fspec.canonical] = fspec.data_type
        if fspec.required:
            field_required.add(fspec.canonical)

    # 3. Row-level validation
    seen_order_ids: dict[str, int] = {}  # order_id -> first row_index
    today = datetime.now().strftime("%Y-%m-%d")

    for i, row in enumerate(rows):
        # Required field null checks
        for req in field_required:
            if req in row and _is_null_or_empty(row.get(req)):
                result.add_error(
                    ErrorCode.NULL_REQUIRED_FIELD,
                    f"Required field '{req}' is null/empty at row {i}",
                    row_index=i, column=req,
                    raw_value=str(row.get(req)),
                )

        # Type checks
        for col, val in row.items():
            if _is_null_or_empty(val):
                continue
            expected_type = field_types.get(col)
            if not expected_type:
                continue

            if expected_type == "float" and not _is_numeric(val):
                result.add_error(
                    ErrorCode.INVALID_NUMERIC,
                    f"Column '{col}' expected numeric, got '{val}' at row {i}",
                    row_index=i, column=col, raw_value=str(val),
                )

            if expected_type == "int":
                if not _is_numeric(val):
                    result.add_error(
                        ErrorCode.INVALID_INTEGER,
                        f"Column '{col}' expected integer, got '{val}' at row {i}",
                        row_index=i, column=col, raw_value=str(val),
                    )

            if expected_type == "date":
                if isinstance(val, str) and val.strip() and not _is_date_like(val):
                    result.add_warning(
                        ErrorCode.INVALID_DATE,
                        f"Column '{col}' may have invalid date format: '{val}' at row {i}",
                        row_index=i, column=col, raw_value=str(val),
                    )

        # Negative amount warnings for financial fields
        for money_col in ("gross_sales", "net_sales", "amount", "gross_amount", "net_amount",
                          "labor_cost", "modifier_price"):
            val = row.get(money_col)
            if val is not None:
                num = _to_float_safe(val)
                if num is not None and num < 0:
                    result.add_warning(
                        ErrorCode.NEGATIVE_AMOUNT,
                        f"Negative amount in '{money_col}': {num} at row {i}",
                        row_index=i, column=money_col, raw_value=str(val),
                    )

        # Duplicate order_id detection (for order-based reports)
        order_id = row.get("order_id")
        location = row.get("location", "")
        if order_id and report_type == ToastReportType.ORDER_DETAILS:
            dedup_key = f"{location}|{order_id}"
            if dedup_key in seen_order_ids:
                result.add_warning(
                    ErrorCode.DUPLICATE_ORDER,
                    f"Duplicate order_id '{order_id}' at row {i} (first seen row {seen_order_ids[dedup_key]})",
                    row_index=i, column="order_id", raw_value=str(order_id),
                )
            else:
                seen_order_ids[dedup_key] = i

        # Future date warning
        biz_date = row.get("business_date")
        if biz_date and isinstance(biz_date, str):
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})", biz_date)
            if date_match and date_match.group(1) > today:
                result.add_warning(
                    ErrorCode.FUTURE_DATE,
                    f"Future business_date '{biz_date}' at row {i}",
                    row_index=i, column="business_date", raw_value=biz_date,
                )

    logger.info("Validated %s: %s", report_type.value, result.summary())
    return result


# ── Report-specific validators ───────────────────────────────────────────────
# These add extra checks beyond the generic validator.

def validate_order_details(rows: list[dict[str, Any]]) -> ValidationResult:
    """Validate Order Details with extra business rules."""
    result = validate_toast_report(rows, ToastReportType.ORDER_DETAILS)

    for i, row in enumerate(rows):
        gross = _to_float_safe(row.get("gross_sales"))
        net = _to_float_safe(row.get("net_sales"))
        if gross is not None and net is not None and net > gross * 1.01:
            result.add_warning(
                "NET_EXCEEDS_GROSS",
                f"net_sales ({net}) > gross_sales ({gross}) at row {i}",
                row_index=i,
            )
    return result


def validate_payment_details(rows: list[dict[str, Any]]) -> ValidationResult:
    """Validate Payment Details."""
    result = validate_toast_report(rows, ToastReportType.PAYMENT_DETAILS)

    for i, row in enumerate(rows):
        ptype = row.get("payment_type")
        if _is_null_or_empty(ptype):
            result.add_error(
                ErrorCode.NULL_REQUIRED_FIELD,
                f"payment_type is null at row {i}",
                row_index=i, column="payment_type",
            )
    return result


def validate_item_selection(rows: list[dict[str, Any]]) -> ValidationResult:
    """Validate Item Selection Details."""
    return validate_toast_report(rows, ToastReportType.ITEM_SELECTION)


def validate_modifier_selection(rows: list[dict[str, Any]]) -> ValidationResult:
    """Validate Modifier Selection Details."""
    return validate_toast_report(rows, ToastReportType.MODIFIER_SELECTION)


def validate_labor(rows: list[dict[str, Any]]) -> ValidationResult:
    """Validate Time Entries / Labor."""
    result = validate_toast_report(rows, ToastReportType.TIME_ENTRIES)

    for i, row in enumerate(rows):
        reg = _to_float_safe(row.get("regular_hours"))
        ot = _to_float_safe(row.get("overtime_hours"))
        if reg is not None and reg > 24:
            result.add_warning(
                "EXCESSIVE_HOURS",
                f"regular_hours ({reg}) exceeds 24 at row {i}",
                row_index=i, column="regular_hours",
            )
        if ot is not None and ot > 16:
            result.add_warning(
                "EXCESSIVE_OT",
                f"overtime_hours ({ot}) exceeds 16 at row {i}",
                row_index=i, column="overtime_hours",
            )
    return result


# ── Validator dispatch ───────────────────────────────────────────────────────

_VALIDATORS = {
    ToastReportType.ORDER_DETAILS: validate_order_details,
    ToastReportType.PAYMENT_DETAILS: validate_payment_details,
    ToastReportType.ITEM_SELECTION: validate_item_selection,
    ToastReportType.MODIFIER_SELECTION: validate_modifier_selection,
    ToastReportType.TIME_ENTRIES: validate_labor,
}


def validate(rows: list[dict[str, Any]], report_type: ToastReportType) -> ValidationResult:
    """Validate rows using the appropriate report-specific validator."""
    validator = _VALIDATORS.get(report_type, lambda r: validate_toast_report(r, report_type))
    return validator(rows)
