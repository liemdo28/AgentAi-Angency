"""
toast_report_types.py — Toast POS report type definitions, detection, and field mappings.

Supports all Toast data export report types:
  Mandatory:  OrderDetails, PaymentDetails, ItemSelectionDetails,
              ModifierSelectionDetails, ProductMix
  Recommended: TimeEntries, Accounting, Menu
  Optional:    KitchenDetails, CashManagement
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Report Type Enum ─────────────────────────────────────────────────────────

class ToastReportType(str, Enum):
    ORDER_DETAILS = "order_details"
    PAYMENT_DETAILS = "payment_details"
    ITEM_SELECTION = "item_selection"
    MODIFIER_SELECTION = "modifier_selection"
    PRODUCT_MIX = "product_mix"
    TIME_ENTRIES = "time_entries"
    ACCOUNTING = "accounting"
    MENU = "menu"
    KITCHEN_DETAILS = "kitchen_details"
    CASH_MANAGEMENT = "cash_management"
    UNKNOWN = "unknown"


# ── Field Spec ───────────────────────────────────────────────────────────────

@dataclass
class FieldSpec:
    """Specification for a single field in a Toast report."""
    canonical: str          # Our normalized field name
    source_aliases: list[str] = field(default_factory=list)  # Possible column names in source
    required: bool = False
    data_type: str = "str"  # str, int, float, date, datetime, bool
    description: str = ""


# ── Report Definitions ───────────────────────────────────────────────────────

@dataclass
class ToastReportDefinition:
    """Full definition for a Toast report type."""
    report_type: ToastReportType
    display_name: str
    description: str
    filename_patterns: list[str]   # regex patterns to match filenames
    required_columns: list[str]    # canonical column names that MUST exist
    fields: list[FieldSpec]        # all known fields
    raw_table: str                 # target raw table name
    phase: str = "mandatory"       # mandatory | recommended | optional

    @property
    def all_source_aliases(self) -> dict[str, list[str]]:
        """Map canonical field name -> list of source aliases."""
        return {f.canonical: f.source_aliases for f in self.fields}

    @property
    def canonical_names(self) -> list[str]:
        return [f.canonical for f in self.fields]


# ── Filename patterns ────────────────────────────────────────────────────────
# These match common Toast export naming conventions and our own convention.

_ORDER_PATTERNS = [
    r"(?i)order\s*details",
    r"(?i)orderdetails",
    r"(?i)\d{4}-\d{2}-\d{2}_orderdetails",
]

_PAYMENT_PATTERNS = [
    r"(?i)payment\s*details",
    r"(?i)paymentdetails",
    r"(?i)\d{4}-\d{2}-\d{2}_paymentdetails",
]

_ITEM_PATTERNS = [
    r"(?i)item\s*selection\s*details",
    r"(?i)itemselectiondetails",
    r"(?i)\d{4}-\d{2}-\d{2}_itemselectiondetails",
]

_MODIFIER_PATTERNS = [
    r"(?i)modifier[s]?\s*selection\s*details",
    r"(?i)modifier[s]?selectiondetails",
    r"(?i)\d{4}-\d{2}-\d{2}_modifier[s]?selectiondetails",
]

_PRODUCT_MIX_PATTERNS = [
    r"(?i)product\s*mix",
    r"(?i)productmix",
    r"(?i)\d{4}-\d{2}-\d{2}_productmix",
]

_TIME_ENTRIES_PATTERNS = [
    r"(?i)time\s*entr",
    r"(?i)timeentr",
    r"(?i)labor\s*summary",
    r"(?i)payroll\s*export",
    r"(?i)\d{4}-\d{2}-\d{2}_timeentries",
]

_ACCOUNTING_PATTERNS = [
    r"(?i)accounting",
    r"(?i)\d{4}-\d{2}-\d{2}_accounting",
]

_MENU_PATTERNS = [
    r"(?i)^menu[_\s\.]",
    r"(?i)menu\s*export",
    r"(?i)\d{4}-\d{2}-\d{2}_menu",
]

_KITCHEN_PATTERNS = [
    r"(?i)kitchen\s*details",
    r"(?i)kitchendetails",
]

_CASH_PATTERNS = [
    r"(?i)cash\s*management",
    r"(?i)cashmanagement",
]


# ── Field definitions for each report ────────────────────────────────────────

ORDER_DETAILS_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name", "restaurant_name"], required=True),
    FieldSpec("order_id", ["order_id", "orderid", "order id", "toast_order_id"], required=True, data_type="str"),
    FieldSpec("order_number", ["order_#", "order_number", "order number", "order#", "ordernumber"], data_type="str"),
    FieldSpec("business_date", ["business_date", "businessdate", "business date", "biz_date"], required=True, data_type="date"),
    FieldSpec("sent_date", ["sent_date", "sentdate", "sent date", "order_date"], data_type="datetime"),
    FieldSpec("closed_date", ["closed_date", "closeddate", "closed date", "close_date"], data_type="datetime"),
    FieldSpec("dining_option", ["dining_option", "diningoption", "dining option", "order_type", "service_type"]),
    FieldSpec("source", ["source", "order_source", "channel"]),
    FieldSpec("gross_sales", ["gross_sales", "grosssales", "gross sales", "gross_amount", "total_gross"], required=True, data_type="float"),
    FieldSpec("net_sales", ["net_sales", "netsales", "net sales", "net_amount", "total_net"], data_type="float"),
    FieldSpec("tax", ["tax", "tax_amount", "total_tax", "taxes"], data_type="float"),
    FieldSpec("tips", ["tips", "tip", "tip_amount", "gratuity"], data_type="float"),
    FieldSpec("discount_total", ["discount", "discounts", "discount_total", "discount_amount", "total_discount"], data_type="float"),
    FieldSpec("void_status", ["voided", "void", "void_status", "is_void"], data_type="str"),
    FieldSpec("refund_amount", ["refund", "refund_amount", "refunds"], data_type="float"),
    FieldSpec("check_status", ["check_status", "status", "order_status"]),
    FieldSpec("guest_count", ["guests", "guest_count", "covers", "number_of_guests", "party_size"], data_type="int"),
    FieldSpec("server", ["server", "employee", "employee_name", "staff"]),
    FieldSpec("revenue_center", ["revenue_center", "revenuecenter", "revenue center"]),
]

PAYMENT_DETAILS_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name"], required=True),
    FieldSpec("order_id", ["order_id", "orderid", "order id"], required=True, data_type="str"),
    FieldSpec("order_number", ["order_#", "order_number", "order number", "order#"]),
    FieldSpec("payment_type", ["payment_type", "paymenttype", "payment type", "tender_type", "type"], required=True),
    FieldSpec("amount", ["amount", "payment_amount", "total", "paid_amount"], required=True, data_type="float"),
    FieldSpec("tip", ["tip", "tip_amount", "gratuity"], data_type="float"),
    FieldSpec("payment_status", ["payment_status", "status", "state"]),
    FieldSpec("card_type", ["card_type", "cardtype", "card type", "card_brand"]),
    FieldSpec("close_date", ["close_date", "closed_date", "paid_date", "payment_date"], data_type="datetime"),
    FieldSpec("business_date", ["business_date", "businessdate", "business date"], data_type="date"),
    FieldSpec("refund_amount", ["refund", "refund_amount"], data_type="float"),
    FieldSpec("void_status", ["voided", "void", "void_status"], data_type="str"),
]

ITEM_SELECTION_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name"], required=True),
    FieldSpec("order_id", ["order_id", "orderid", "order id"], required=True, data_type="str"),
    FieldSpec("order_number", ["order_#", "order_number", "order number", "order#"]),
    FieldSpec("sent_date", ["sent_date", "sentdate", "sent date", "order_date"], data_type="datetime"),
    FieldSpec("item_name", ["item", "item_name", "menu_item", "selection", "item_selection"], required=True),
    FieldSpec("sales_category", ["sales_category", "category", "sales category", "menu_category"]),
    FieldSpec("menu_group", ["menu_group", "menugroup", "menu group", "menu_subgroup"]),
    FieldSpec("qty", ["qty", "quantity", "count", "item_qty"], required=True, data_type="int"),
    FieldSpec("gross_amount", ["gross_price", "gross_amount", "gross", "price", "gross_sales"], required=True, data_type="float"),
    FieldSpec("discount_amount", ["discount", "discount_amount", "item_discount"], data_type="float"),
    FieldSpec("net_amount", ["net_price", "net_amount", "net", "net_sales"], data_type="float"),
    FieldSpec("server", ["server", "employee", "employee_name"]),
    FieldSpec("dining_option", ["dining_option", "diningoption", "dining option"]),
    FieldSpec("tax", ["tax", "tax_amount", "item_tax"], data_type="float"),
    FieldSpec("business_date", ["business_date", "businessdate", "business date"], data_type="date"),
]

MODIFIER_SELECTION_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name"], required=True),
    FieldSpec("order_id", ["order_id", "orderid", "order id"], required=True, data_type="str"),
    FieldSpec("order_number", ["order_#", "order_number", "order number", "order#"]),
    FieldSpec("parent_item", ["parent_item", "parent", "item", "menu_item", "item_name", "parent_menu_selection"]),
    FieldSpec("modifier_name", ["modifier", "modifier_name", "option", "modifier_option", "option_group_name"], required=True),
    FieldSpec("qty", ["qty", "quantity", "count"], data_type="int"),
    FieldSpec("modifier_price", ["modifier_price", "price", "amount", "option_price"], data_type="float"),
    FieldSpec("sent_date", ["sent_date", "sentdate", "sent date", "order_date"], data_type="datetime"),
    FieldSpec("business_date", ["business_date", "businessdate", "business date"], data_type="date"),
]

PRODUCT_MIX_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name"], required=True),
    FieldSpec("business_date", ["date", "business_date", "businessdate", "business date"], data_type="date"),
    FieldSpec("item_name", ["item", "item_name", "menu_item", "product"], required=True),
    FieldSpec("category", ["category", "sales_category", "menu_category", "group"]),
    FieldSpec("qty", ["qty", "quantity", "count", "items_sold", "qty_sold"], required=True, data_type="int"),
    FieldSpec("gross_sales", ["gross_sales", "gross", "gross_amount"], data_type="float"),
    FieldSpec("net_sales", ["net_sales", "net", "net_amount"], data_type="float"),
    FieldSpec("discount", ["discount", "discount_amount", "discounts"], data_type="float"),
    FieldSpec("mix_pct", ["mix_%", "mix_pct", "mix_percentage", "pct_of_total", "% of total"], data_type="float"),
]

TIME_ENTRIES_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name"], required=True),
    FieldSpec("employee", ["employee", "employee_name", "name", "staff", "team_member"], required=True),
    FieldSpec("role", ["role", "position", "job", "job_title", "job_name"]),
    FieldSpec("clock_in", ["clock_in", "clockin", "in_time", "start_time", "punch_in"], required=True, data_type="datetime"),
    FieldSpec("clock_out", ["clock_out", "clockout", "out_time", "end_time", "punch_out"], data_type="datetime"),
    FieldSpec("regular_hours", ["regular_hours", "reg_hours", "hours", "total_hours"], data_type="float"),
    FieldSpec("overtime_hours", ["overtime_hours", "ot_hours", "overtime", "ot"], data_type="float"),
    FieldSpec("labor_cost", ["labor_cost", "cost", "total_cost", "pay", "wages"], data_type="float"),
    FieldSpec("business_date", ["business_date", "businessdate", "business date", "date", "shift_date"], data_type="date"),
    FieldSpec("hourly_rate", ["hourly_rate", "rate", "pay_rate"], data_type="float"),
    FieldSpec("tips", ["tips", "tip_amount", "declared_tips"], data_type="float"),
]

ACCOUNTING_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store", "store_name"], required=True),
    FieldSpec("account_code", ["account_code", "code", "gl_code", "account_number", "account"]),
    FieldSpec("account_name", ["account_name", "name", "description", "gl_name"]),
    FieldSpec("revenue_bucket", ["revenue_bucket", "category", "type", "account_type"]),
    FieldSpec("tax_bucket", ["tax_bucket", "tax_category", "tax_type"]),
    FieldSpec("tender_bucket", ["tender_bucket", "tender_type", "payment_category"]),
    FieldSpec("business_date", ["date", "business_date", "businessdate", "period"], data_type="date"),
    FieldSpec("amount", ["amount", "total", "value", "net_amount"], required=True, data_type="float"),
    FieldSpec("debit", ["debit", "debit_amount"], data_type="float"),
    FieldSpec("credit", ["credit", "credit_amount"], data_type="float"),
]

MENU_FIELDS = [
    FieldSpec("item_id", ["item_id", "id", "menu_item_id", "toast_item_id"]),
    FieldSpec("item_name", ["item_name", "name", "menu_item", "item"], required=True),
    FieldSpec("menu", ["menu", "menu_name", "menu_group"]),
    FieldSpec("category", ["category", "sales_category", "menu_category", "group"]),
    FieldSpec("subgroup", ["subgroup", "sub_group", "subcategory", "sub_category"]),
    FieldSpec("price", ["price", "base_price", "default_price", "amount"], data_type="float"),
    FieldSpec("active", ["active", "status", "is_active", "archived", "visibility"], data_type="str"),
    FieldSpec("location", ["location", "restaurant", "store", "store_name", "applicable_locations"]),
    FieldSpec("plu", ["plu", "sku", "plu_code"]),
    FieldSpec("description", ["description", "item_description"]),
]

KITCHEN_DETAILS_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store"], required=True),
    FieldSpec("order_id", ["order_id", "orderid", "order id"], required=True, data_type="str"),
    FieldSpec("item_name", ["item", "item_name", "menu_item"]),
    FieldSpec("station", ["station", "kitchen_station", "prep_station"]),
    FieldSpec("ticket_time_sec", ["ticket_time", "ticket_time_sec", "fulfillment_time"], data_type="float"),
    FieldSpec("created_at", ["created_date", "created_at", "sent_date"], data_type="datetime"),
    FieldSpec("fulfilled_at", ["fulfilled_date", "fulfilled_at", "done_date"], data_type="datetime"),
    FieldSpec("business_date", ["business_date", "businessdate", "business date"], data_type="date"),
]

CASH_MANAGEMENT_FIELDS = [
    FieldSpec("location", ["location", "restaurant", "store"], required=True),
    FieldSpec("business_date", ["business_date", "date", "shift_date"], required=True, data_type="date"),
    FieldSpec("employee", ["employee", "employee_name", "cashier"]),
    FieldSpec("drawer_name", ["drawer", "drawer_name", "register"]),
    FieldSpec("expected_amount", ["expected", "expected_amount", "expected_cash"], data_type="float"),
    FieldSpec("actual_amount", ["actual", "actual_amount", "actual_cash"], data_type="float"),
    FieldSpec("over_short", ["over_short", "difference", "variance", "over/short"], data_type="float"),
    FieldSpec("close_time", ["close_time", "closed_at", "drawer_close"], data_type="datetime"),
]


# ── Report Registry ──────────────────────────────────────────────────────────

REPORT_DEFINITIONS: dict[ToastReportType, ToastReportDefinition] = {
    ToastReportType.ORDER_DETAILS: ToastReportDefinition(
        report_type=ToastReportType.ORDER_DETAILS,
        display_name="Order Details",
        description="Revenue trend, AOV, daypart, source/channel, store-level sales",
        filename_patterns=_ORDER_PATTERNS,
        required_columns=["location", "order_id", "business_date", "gross_sales"],
        fields=ORDER_DETAILS_FIELDS,
        raw_table="raw_order_details",
        phase="mandatory",
    ),
    ToastReportType.PAYMENT_DETAILS: ToastReportDefinition(
        report_type=ToastReportType.PAYMENT_DETAILS,
        display_name="Payment Details",
        description="Finance breakdown, payment mix, reconciliation",
        filename_patterns=_PAYMENT_PATTERNS,
        required_columns=["order_id", "payment_type", "amount"],
        fields=PAYMENT_DETAILS_FIELDS,
        raw_table="raw_payment_details",
        phase="mandatory",
    ),
    ToastReportType.ITEM_SELECTION: ToastReportDefinition(
        report_type=ToastReportType.ITEM_SELECTION,
        display_name="Item Selection Details",
        description="Top selling items, category mix, menu performance",
        filename_patterns=_ITEM_PATTERNS,
        required_columns=["order_id", "item_name", "qty"],
        fields=ITEM_SELECTION_FIELDS,
        raw_table="raw_item_selection",
        phase="mandatory",
    ),
    ToastReportType.MODIFIER_SELECTION: ToastReportDefinition(
        report_type=ToastReportType.MODIFIER_SELECTION,
        display_name="Modifier Selection Details",
        description="Customization analysis, attach rate, upsell/cross-sell",
        filename_patterns=_MODIFIER_PATTERNS,
        required_columns=["order_id", "modifier_name"],
        fields=MODIFIER_SELECTION_FIELDS,
        raw_table="raw_modifier_selection",
        phase="mandatory",
    ),
    ToastReportType.PRODUCT_MIX: ToastReportDefinition(
        report_type=ToastReportType.PRODUCT_MIX,
        display_name="Product Mix (All Items)",
        description="Item/category ranking, menu engineering, store comparison",
        filename_patterns=_PRODUCT_MIX_PATTERNS,
        required_columns=["item_name", "qty"],
        fields=PRODUCT_MIX_FIELDS,
        raw_table="raw_product_mix",
        phase="mandatory",
    ),
    ToastReportType.TIME_ENTRIES: ToastReportDefinition(
        report_type=ToastReportType.TIME_ENTRIES,
        display_name="Time Entries / Labor",
        description="Labor cost, sales per labor hour, staffing, payroll",
        filename_patterns=_TIME_ENTRIES_PATTERNS,
        required_columns=["employee", "clock_in"],
        fields=TIME_ENTRIES_FIELDS,
        raw_table="raw_time_entries",
        phase="recommended",
    ),
    ToastReportType.ACCOUNTING: ToastReportDefinition(
        report_type=ToastReportType.ACCOUNTING,
        display_name="Accounting",
        description="GL mapping, bookkeeping, CFO reconciliation",
        filename_patterns=_ACCOUNTING_PATTERNS,
        required_columns=["amount"],
        fields=ACCOUNTING_FIELDS,
        raw_table="raw_accounting",
        phase="recommended",
    ),
    ToastReportType.MENU: ToastReportDefinition(
        report_type=ToastReportType.MENU,
        display_name="Menu",
        description="Item master, category mapping, item lifecycle",
        filename_patterns=_MENU_PATTERNS,
        required_columns=["item_name"],
        fields=MENU_FIELDS,
        raw_table="raw_menu",
        phase="recommended",
    ),
    ToastReportType.KITCHEN_DETAILS: ToastReportDefinition(
        report_type=ToastReportType.KITCHEN_DETAILS,
        display_name="Kitchen Details",
        description="Ticket time, prep time, kitchen bottleneck",
        filename_patterns=_KITCHEN_PATTERNS,
        required_columns=["order_id"],
        fields=KITCHEN_DETAILS_FIELDS,
        raw_table="raw_kitchen_details",
        phase="optional",
    ),
    ToastReportType.CASH_MANAGEMENT: ToastReportDefinition(
        report_type=ToastReportType.CASH_MANAGEMENT,
        display_name="Cash Management",
        description="Cash handling, drawer reconciliation",
        filename_patterns=_CASH_PATTERNS,
        required_columns=["business_date"],
        fields=CASH_MANAGEMENT_FIELDS,
        raw_table="raw_cash_management",
        phase="optional",
    ),
}


# ── Detection Functions ──────────────────────────────────────────────────────

def detect_report_type_by_filename(filename: str) -> ToastReportType:
    """Detect Toast report type from filename using regex patterns."""
    basename = os.path.splitext(os.path.basename(filename))[0]
    for report_type, definition in REPORT_DEFINITIONS.items():
        for pattern in definition.filename_patterns:
            if re.search(pattern, basename):
                return report_type
    return ToastReportType.UNKNOWN


def detect_report_type_by_columns(columns: list[str]) -> ToastReportType:
    """
    Detect Toast report type by matching column names against field aliases.
    Uses a scoring approach: the report type with the highest match wins.
    """
    if not columns:
        return ToastReportType.UNKNOWN

    normalized_cols = {c.strip().lower().replace(" ", "_") for c in columns}
    best_type = ToastReportType.UNKNOWN
    best_score = 0.0

    for report_type, definition in REPORT_DEFINITIONS.items():
        matched = 0
        required_matched = 0
        total_required = len(definition.required_columns)

        for fspec in definition.fields:
            aliases = {a.strip().lower().replace(" ", "_") for a in fspec.source_aliases}
            if normalized_cols & aliases:
                matched += 1
                if fspec.canonical in definition.required_columns:
                    required_matched += 1

        # Must match all required columns
        if total_required > 0 and required_matched < total_required:
            continue

        # Score = ratio of matched fields
        score = matched / len(definition.fields) if definition.fields else 0
        if score > best_score:
            best_score = score
            best_type = report_type

    return best_type


def detect_report_type(filename: str, columns: list[str] | None = None) -> ToastReportType:
    """
    Detect report type using filename first, falling back to column analysis.
    """
    result = detect_report_type_by_filename(filename)
    if result != ToastReportType.UNKNOWN:
        return result
    if columns:
        return detect_report_type_by_columns(columns)
    return ToastReportType.UNKNOWN


def get_definition(report_type: ToastReportType) -> ToastReportDefinition | None:
    """Get the full definition for a report type."""
    return REPORT_DEFINITIONS.get(report_type)


def map_columns_to_canonical(
    source_columns: list[str],
    report_type: ToastReportType,
) -> dict[str, str]:
    """
    Map source column names to canonical field names.
    Returns {source_column: canonical_name} for matched columns.
    Unmatched source columns are excluded.
    """
    definition = REPORT_DEFINITIONS.get(report_type)
    if not definition:
        return {}

    mapping: dict[str, str] = {}
    for source_col in source_columns:
        norm = source_col.strip().lower().replace(" ", "_")
        for fspec in definition.fields:
            aliases = {a.strip().lower().replace(" ", "_") for a in fspec.source_aliases}
            if norm in aliases:
                mapping[source_col] = fspec.canonical
                break

    return mapping


def get_coverage_matrix() -> list[dict[str, Any]]:
    """
    Return a coverage matrix showing all report types and their support status.
    Used for reporting/auditing which reports are supported.
    """
    matrix = []
    for report_type, defn in REPORT_DEFINITIONS.items():
        matrix.append({
            "report_type": report_type.value,
            "display_name": defn.display_name,
            "phase": defn.phase,
            "raw_table": defn.raw_table,
            "required_columns": defn.required_columns,
            "total_fields": len(defn.fields),
            "required_fields": sum(1 for f in defn.fields if f.required),
            "detect": True,
            "parse": True,
            "validate": True,
            "raw_load": True,
            "normalize": True,
        })
    return matrix
