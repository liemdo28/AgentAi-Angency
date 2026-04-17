"""
toast_schema.py — Toast report ingestion database schema.

Tables:
  - upload_files: file-level tracking with SHA-256 dedup
  - raw_*: 8 raw tables mirroring Toast export structure
  - normalized: 10 clean, typed, deduped tables for dashboards
  - config: store_aliases, channel_aliases, item_aliases
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

TOAST_DB_PATH = Path(__file__).parent.parent.parent / "data" / "toast.db"

TOAST_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================================
-- FILE TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS upload_files (
    id              TEXT PRIMARY KEY,
    google_file_id  TEXT,
    file_name       TEXT NOT NULL,
    report_type     TEXT NOT NULL,
    store_id        TEXT,
    business_date_start TEXT,
    business_date_end   TEXT,
    file_hash       TEXT NOT NULL,
    file_size_bytes INTEGER,
    row_count       INTEGER DEFAULT 0,
    uploaded_at     TEXT DEFAULT (datetime('now')),
    imported_at     TEXT,
    status          TEXT DEFAULT 'pending',  -- pending, processing, completed, failed, duplicate
    error_message   TEXT,
    error_count     INTEGER DEFAULT 0,
    warning_count   INTEGER DEFAULT 0,
    source          TEXT DEFAULT 'manual'    -- manual, gdrive, api
);
CREATE INDEX IF NOT EXISTS idx_upload_hash ON upload_files(file_hash);
CREATE INDEX IF NOT EXISTS idx_upload_status ON upload_files(status);
CREATE INDEX IF NOT EXISTS idx_upload_report ON upload_files(report_type);
CREATE INDEX IF NOT EXISTS idx_upload_store ON upload_files(store_id);
CREATE INDEX IF NOT EXISTS idx_upload_gdrive ON upload_files(google_file_id);

-- ============================================================================
-- RAW TABLES — mirror Toast CSV structure, all TEXT for safety
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw_order_details (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    order_id        TEXT,
    order_number    TEXT,
    business_date   TEXT,
    sent_date       TEXT,
    closed_date     TEXT,
    dining_option   TEXT,
    source          TEXT,
    gross_sales     TEXT,
    net_sales       TEXT,
    tax             TEXT,
    tips            TEXT,
    discount_total  TEXT,
    void_status     TEXT,
    refund_amount   TEXT,
    check_status    TEXT,
    guest_count     TEXT,
    server          TEXT,
    revenue_center  TEXT,
    raw_json        TEXT,  -- full original row as JSON
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_orders_upload ON raw_order_details(upload_file_id);
CREATE INDEX IF NOT EXISTS idx_raw_orders_order ON raw_order_details(order_id);

CREATE TABLE IF NOT EXISTS raw_payment_details (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    order_id        TEXT,
    order_number    TEXT,
    payment_type    TEXT,
    amount          TEXT,
    tip             TEXT,
    payment_status  TEXT,
    card_type       TEXT,
    close_date      TEXT,
    business_date   TEXT,
    refund_amount   TEXT,
    void_status     TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_payments_upload ON raw_payment_details(upload_file_id);
CREATE INDEX IF NOT EXISTS idx_raw_payments_order ON raw_payment_details(order_id);

CREATE TABLE IF NOT EXISTS raw_item_selection (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    order_id        TEXT,
    order_number    TEXT,
    sent_date       TEXT,
    item_name       TEXT,
    sales_category  TEXT,
    menu_group      TEXT,
    qty             TEXT,
    gross_amount    TEXT,
    discount_amount TEXT,
    net_amount      TEXT,
    server          TEXT,
    dining_option   TEXT,
    tax             TEXT,
    business_date   TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_items_upload ON raw_item_selection(upload_file_id);
CREATE INDEX IF NOT EXISTS idx_raw_items_order ON raw_item_selection(order_id);

CREATE TABLE IF NOT EXISTS raw_modifier_selection (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    order_id        TEXT,
    order_number    TEXT,
    parent_item     TEXT,
    modifier_name   TEXT,
    qty             TEXT,
    modifier_price  TEXT,
    sent_date       TEXT,
    business_date   TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_modifiers_upload ON raw_modifier_selection(upload_file_id);
CREATE INDEX IF NOT EXISTS idx_raw_modifiers_order ON raw_modifier_selection(order_id);

CREATE TABLE IF NOT EXISTS raw_product_mix (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    business_date   TEXT,
    item_name       TEXT,
    category        TEXT,
    qty             TEXT,
    gross_sales     TEXT,
    net_sales       TEXT,
    discount        TEXT,
    mix_pct         TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_pmix_upload ON raw_product_mix(upload_file_id);

CREATE TABLE IF NOT EXISTS raw_time_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    employee        TEXT,
    role            TEXT,
    clock_in        TEXT,
    clock_out       TEXT,
    regular_hours   TEXT,
    overtime_hours  TEXT,
    labor_cost      TEXT,
    business_date   TEXT,
    hourly_rate     TEXT,
    tips            TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_labor_upload ON raw_time_entries(upload_file_id);

CREATE TABLE IF NOT EXISTS raw_accounting (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    account_code    TEXT,
    account_name    TEXT,
    revenue_bucket  TEXT,
    tax_bucket      TEXT,
    tender_bucket   TEXT,
    business_date   TEXT,
    amount          TEXT,
    debit           TEXT,
    credit          TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_acct_upload ON raw_accounting(upload_file_id);

CREATE TABLE IF NOT EXISTS raw_menu (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    item_id         TEXT,
    item_name       TEXT,
    menu            TEXT,
    category        TEXT,
    subgroup        TEXT,
    price           TEXT,
    active          TEXT,
    location        TEXT,
    plu             TEXT,
    description     TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_menu_upload ON raw_menu(upload_file_id);

CREATE TABLE IF NOT EXISTS raw_kitchen_details (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    order_id        TEXT,
    item_name       TEXT,
    station         TEXT,
    ticket_time_sec TEXT,
    created_at      TEXT,
    fulfilled_at    TEXT,
    business_date   TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_kitchen_upload ON raw_kitchen_details(upload_file_id);

CREATE TABLE IF NOT EXISTS raw_cash_management (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT NOT NULL REFERENCES upload_files(id),
    row_index       INTEGER NOT NULL,
    location        TEXT,
    business_date   TEXT,
    employee        TEXT,
    drawer_name     TEXT,
    expected_amount TEXT,
    actual_amount   TEXT,
    over_short      TEXT,
    close_time      TEXT,
    raw_json        TEXT,
    UNIQUE(upload_file_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_raw_cash_upload ON raw_cash_management(upload_file_id);

-- ============================================================================
-- NORMALIZED TABLES — typed, deduped, ready for dashboards
-- ============================================================================

CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,  -- location + order_id
    upload_file_id  TEXT REFERENCES upload_files(id),
    store_id        TEXT NOT NULL,
    location_raw    TEXT,
    order_id        TEXT NOT NULL,
    order_number    TEXT,
    business_date   TEXT NOT NULL,
    sent_date       TEXT,
    closed_date     TEXT,
    dining_option   TEXT,
    channel         TEXT,   -- normalized channel
    gross_sales     REAL DEFAULT 0,
    net_sales       REAL DEFAULT 0,
    tax             REAL DEFAULT 0,
    tips            REAL DEFAULT 0,
    discount_total  REAL DEFAULT 0,
    is_void         INTEGER DEFAULT 0,
    refund_amount   REAL DEFAULT 0,
    check_status    TEXT,
    guest_count     INTEGER,
    server          TEXT,
    revenue_center  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, order_id)
);
CREATE INDEX IF NOT EXISTS idx_orders_store_date ON orders(store_id, business_date);
CREATE INDEX IF NOT EXISTS idx_orders_channel ON orders(channel);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT REFERENCES upload_files(id),
    store_id        TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    order_number    TEXT,
    payment_type    TEXT NOT NULL,
    amount          REAL NOT NULL,
    tip             REAL DEFAULT 0,
    payment_status  TEXT,
    card_type       TEXT,
    close_date      TEXT,
    business_date   TEXT,
    refund_amount   REAL DEFAULT 0,
    is_void         INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, order_id, payment_type, amount)
);
CREATE INDEX IF NOT EXISTS idx_payments_store_date ON payments(store_id, business_date);

CREATE TABLE IF NOT EXISTS order_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT REFERENCES upload_files(id),
    store_id        TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    order_number    TEXT,
    sent_date       TEXT,
    business_date   TEXT,
    raw_item_name   TEXT NOT NULL,
    item_name       TEXT NOT NULL,  -- normalized
    sales_category  TEXT,
    menu_group      TEXT,
    qty             INTEGER DEFAULT 1,
    gross_amount    REAL DEFAULT 0,
    discount_amount REAL DEFAULT 0,
    net_amount      REAL DEFAULT 0,
    tax             REAL DEFAULT 0,
    server          TEXT,
    dining_option   TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_oi_store_date ON order_items(store_id, business_date);
CREATE INDEX IF NOT EXISTS idx_oi_item ON order_items(item_name);

CREATE TABLE IF NOT EXISTS order_item_modifiers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT REFERENCES upload_files(id),
    store_id        TEXT NOT NULL,
    order_id        TEXT NOT NULL,
    parent_item     TEXT,
    modifier_name   TEXT NOT NULL,
    qty             INTEGER DEFAULT 1,
    modifier_price  REAL DEFAULT 0,
    sent_date       TEXT,
    business_date   TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_oim_store ON order_item_modifiers(store_id);
CREATE INDEX IF NOT EXISTS idx_oim_order ON order_item_modifiers(order_id);

CREATE TABLE IF NOT EXISTS daily_store_sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        TEXT NOT NULL,
    business_date   TEXT NOT NULL,
    order_count     INTEGER DEFAULT 0,
    gross_sales     REAL DEFAULT 0,
    net_sales       REAL DEFAULT 0,
    tax_total       REAL DEFAULT 0,
    tips_total      REAL DEFAULT 0,
    discount_total  REAL DEFAULT 0,
    refund_total    REAL DEFAULT 0,
    void_count      INTEGER DEFAULT 0,
    avg_order_value REAL DEFAULT 0,
    guest_count     INTEGER DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, business_date)
);

CREATE TABLE IF NOT EXISTS daily_channel_sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        TEXT NOT NULL,
    business_date   TEXT NOT NULL,
    channel         TEXT NOT NULL,
    order_count     INTEGER DEFAULT 0,
    gross_sales     REAL DEFAULT 0,
    net_sales       REAL DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, business_date, channel)
);

CREATE TABLE IF NOT EXISTS daily_item_sales (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        TEXT NOT NULL,
    business_date   TEXT NOT NULL,
    item_name       TEXT NOT NULL,
    sales_category  TEXT,
    qty_sold        INTEGER DEFAULT 0,
    gross_sales     REAL DEFAULT 0,
    net_sales       REAL DEFAULT 0,
    discount_total  REAL DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, business_date, item_name)
);

CREATE TABLE IF NOT EXISTS labor_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        TEXT NOT NULL,
    business_date   TEXT NOT NULL,
    employee        TEXT NOT NULL,
    role            TEXT,
    regular_hours   REAL DEFAULT 0,
    overtime_hours  REAL DEFAULT 0,
    total_hours     REAL DEFAULT 0,
    labor_cost      REAL DEFAULT 0,
    hourly_rate     REAL,
    tips            REAL DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, business_date, employee, role)
);

CREATE TABLE IF NOT EXISTS accounting_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id        TEXT NOT NULL,
    business_date   TEXT NOT NULL,
    account_code    TEXT,
    account_name    TEXT,
    revenue_bucket  TEXT,
    tax_bucket      TEXT,
    tender_bucket   TEXT,
    amount          REAL DEFAULT 0,
    debit           REAL DEFAULT 0,
    credit          REAL DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(store_id, business_date, account_code)
);

CREATE TABLE IF NOT EXISTS menu_items_master (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id         TEXT,
    raw_item_name   TEXT NOT NULL,
    item_name       TEXT NOT NULL,  -- normalized
    menu            TEXT,
    category        TEXT,
    subgroup        TEXT,
    price           REAL,
    is_active       INTEGER DEFAULT 1,
    location        TEXT,
    plu             TEXT,
    description     TEXT,
    first_seen_at   TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(item_name, location)
);

-- ============================================================================
-- CONFIG TABLES — normalization mappings
-- ============================================================================

CREATE TABLE IF NOT EXISTS store_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alias       TEXT NOT NULL UNIQUE,  -- raw name from Toast (lowered, trimmed)
    store_id    TEXT NOT NULL,          -- internal store ID (e.g. B1, B2, RAW)
    store_name  TEXT,                   -- canonical display name
    brand       TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS channel_aliases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alias       TEXT NOT NULL UNIQUE,  -- raw dining option from Toast (lowered)
    channel     TEXT NOT NULL,          -- canonical: dine_in, pickup, delivery, catering, other
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS item_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    alias           TEXT NOT NULL UNIQUE,  -- raw item name (lowered, trimmed)
    canonical_name  TEXT NOT NULL,          -- clean item name
    category        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- ============================================================================
-- INGEST ERROR LOG
-- ============================================================================

CREATE TABLE IF NOT EXISTS toast_ingest_errors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    upload_file_id  TEXT REFERENCES upload_files(id),
    error_code      TEXT NOT NULL,
    severity        TEXT DEFAULT 'error',  -- error, warning, info
    row_index       INTEGER,
    column_name     TEXT,
    message         TEXT NOT NULL,
    raw_value       TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ingest_err_upload ON toast_ingest_errors(upload_file_id);
CREATE INDEX IF NOT EXISTS idx_ingest_err_code ON toast_ingest_errors(error_code);
"""


# ── Default seed data for normalization tables ───────────────────────────────

DEFAULT_STORE_ALIASES = [
    # Bakudan stores
    ("bakudan ramen - the rim", "B1", "Bakudan 1 - THE RIM", "bakudan"),
    ("bakudan the rim", "B1", "Bakudan 1 - THE RIM", "bakudan"),
    ("bakudan 1", "B1", "Bakudan 1 - THE RIM", "bakudan"),
    ("the rim", "B1", "Bakudan 1 - THE RIM", "bakudan"),
    ("bakudan ramen - stone oak", "B2", "Bakudan 2 - STONE OAK", "bakudan"),
    ("bakudan stone oak", "B2", "Bakudan 2 - STONE OAK", "bakudan"),
    ("bakudan 2", "B2", "Bakudan 2 - STONE OAK", "bakudan"),
    ("stone oak", "B2", "Bakudan 2 - STONE OAK", "bakudan"),
    ("bakudan ramen - bandera", "B3", "Bakudan 3 - BANDERA", "bakudan"),
    ("bakudan bandera", "B3", "Bakudan 3 - BANDERA", "bakudan"),
    ("bakudan 3", "B3", "Bakudan 3 - BANDERA", "bakudan"),
    ("bandera", "B3", "Bakudan 3 - BANDERA", "bakudan"),
    # Raw Sushi
    ("raw sushi - stockton", "RAW", "Raw Sushi - Stockton", "raw_sushi"),
    ("raw sushi bistro", "RAW", "Raw Sushi - Stockton", "raw_sushi"),
    ("raw sushi stockton", "RAW", "Raw Sushi - Stockton", "raw_sushi"),
    ("bakudan ramen - stockton", "RAW", "Raw Sushi - Stockton", "raw_sushi"),
    ("bakudan stockton", "RAW", "Raw Sushi - Stockton", "raw_sushi"),
    ("stockton", "RAW", "Raw Sushi - Stockton", "raw_sushi"),
    # Copper
    ("copper", "COPPER", "Copper", "copper"),
    # IFT
    ("ift", "IFT", "IFT", "ift"),
]

DEFAULT_CHANNEL_ALIASES = [
    ("dine in", "dine_in"),
    ("dine-in", "dine_in"),
    ("dine_in", "dine_in"),
    ("eat in", "dine_in"),
    ("for here", "dine_in"),
    ("takeout", "pickup"),
    ("take out", "pickup"),
    ("take-out", "pickup"),
    ("pickup", "pickup"),
    ("pick up", "pickup"),
    ("pick-up", "pickup"),
    ("online ordering", "pickup"),
    ("online order", "pickup"),
    ("delivery", "delivery"),
    ("uber eats", "delivery"),
    ("ubereats", "delivery"),
    ("doordash", "delivery"),
    ("door dash", "delivery"),
    ("grubhub", "delivery"),
    ("grub hub", "delivery"),
    ("postmates", "delivery"),
    ("caviar", "delivery"),
    ("catering", "catering"),
    ("cater", "catering"),
    ("bar", "bar"),
    ("patio", "dine_in"),
]


def init_toast_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Initialize the Toast ingestion database and seed default config data."""
    path = Path(db_path) if db_path else TOAST_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(TOAST_SCHEMA)

    # Seed store aliases
    for alias, store_id, store_name, brand in DEFAULT_STORE_ALIASES:
        conn.execute(
            "INSERT OR IGNORE INTO store_aliases (alias, store_id, store_name, brand) VALUES (?, ?, ?, ?)",
            (alias, store_id, store_name, brand),
        )

    # Seed channel aliases
    for alias, channel in DEFAULT_CHANNEL_ALIASES:
        conn.execute(
            "INSERT OR IGNORE INTO channel_aliases (alias, channel) VALUES (?, ?)",
            (alias, channel),
        )

    conn.commit()
    logger.info("Toast DB initialized at %s", path)
    return conn


def get_toast_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Get a connection to the Toast DB (initializes if needed)."""
    path = Path(db_path) if db_path else TOAST_DB_PATH
    if not path.exists():
        return init_toast_db(path)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
