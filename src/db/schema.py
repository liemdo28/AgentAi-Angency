"""SQL schema for the agency database — 11 tables."""
SQL_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ACCOUNTS -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    industry TEXT,
    brand_guidelines TEXT,
    primary_contact_email TEXT,
    budget_range_usd INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    metadata_json TEXT DEFAULT '{}'
);

-- CAMPAIGNS ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    name TEXT NOT NULL,
    goal TEXT,
    status TEXT DEFAULT 'planning',
    start_date TEXT,
    end_date TEXT,
    budget_usd INTEGER,
    kpis_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

-- TASKS ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    campaign_id TEXT REFERENCES campaigns(id),
    account_id TEXT REFERENCES accounts(id),
    goal TEXT NOT NULL,
    description TEXT,
    task_type TEXT,
    status TEXT DEFAULT 'draft',
    priority INTEGER DEFAULT 2,
    score REAL DEFAULT 0.0,
    kpis_json TEXT DEFAULT '{}',
    kpi_results_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    deadline TEXT,
    sla_deadline TEXT,
    started_at TEXT,
    completed_at TEXT,
    current_department TEXT,
    planning_mode TEXT DEFAULT 'template',
    health_flags_json TEXT DEFAULT '[]',
    retry_count INTEGER DEFAULT 0,
    escalation_count INTEGER DEFAULT 0,
    final_output_text TEXT,
    final_output_json TEXT DEFAULT '{}',
    specialist_outputs_json TEXT DEFAULT '{}',
    notes TEXT
);

-- CAMPAIGN STEPS (persistent per-step state) ----------------------------------
CREATE TABLE IF NOT EXISTS campaign_steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    step_index INTEGER NOT NULL,
    name TEXT,
    from_department TEXT,
    to_department TEXT,
    required_inputs_json TEXT DEFAULT '[]',
    expected_outputs_json TEXT DEFAULT '[]',
    objective TEXT,
    sla_hours INTEGER DEFAULT 24,
    quality_threshold REAL DEFAULT 98.0,
    status TEXT DEFAULT 'pending',
    score REAL DEFAULT 0.0,
    output_text TEXT,
    feedback TEXT,
    completed_at TEXT,
    UNIQUE(task_id, step_index)
);

-- ACCOUNT MEMORY ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_memory (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    relevance_score REAL DEFAULT 1.0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_memory_account
    ON account_memory(account_id, memory_type);

-- CAMPAIGN MEMORY ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campaign_memory (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    event_type TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_campaign_memory
    ON campaign_memory(campaign_id, event_type);

-- KPI METRICS -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kpi_metrics (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    campaign_id TEXT REFERENCES campaigns(id),
    kpi_name TEXT NOT NULL,
    target REAL,
    actual REAL,
    unit TEXT DEFAULT '%',
    recorded_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kpi_task ON kpi_metrics(task_id);

-- REVIEW HISTORY (audit log per step review) ------------------------------------
CREATE TABLE IF NOT EXISTS review_history (
    id TEXT PRIMARY KEY,
    task_id TEXT REFERENCES tasks(id),
    step_name TEXT,
    score REAL,
    threshold REAL,
    decision TEXT,
    mode TEXT DEFAULT 'llm',
    feedback TEXT,
    breakdown_json TEXT DEFAULT '{}',
    retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- AUDIT LOG (CEO actions, escalations) -----------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    actor TEXT NOT NULL,
    action_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details_json TEXT DEFAULT '{}',
    previous_state_json TEXT,
    new_state_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_entity
    ON audit_log(entity_type, entity_id);

-- EMAIL INGESTION QUEUE ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS email_queue (
    id TEXT PRIMARY KEY,
    account_id TEXT REFERENCES accounts(id),
    campaign_id TEXT REFERENCES campaigns(id),
    sender_email TEXT,
    subject TEXT,
    body_text TEXT,
    attachments_json TEXT DEFAULT '[]',
    parsed_content_json TEXT DEFAULT '{}',
    routing_decision TEXT,
    linked_task_id TEXT REFERENCES tasks(id),
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    received_at TEXT DEFAULT (datetime('now')),
    processed_at TEXT
);

-- SCHEMA MIGRATION TRACKING -----------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);
"""
