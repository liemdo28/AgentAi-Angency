"""
Control Plane schema — extends the existing agency DB with orchestrator tables.

These tables live alongside the 11 existing tables (accounts, campaigns, tasks, etc.)
and add the goal → agent → job → approval layer that powers the control plane.
"""

CONTROL_PLANE_SCHEMA = """
-- GOALS -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    owner TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- CONTROL PLANE AGENTS --------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_agents (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    model TEXT,
    budget_limit REAL DEFAULT 50.0,
    status TEXT DEFAULT 'active',
    config_json TEXT DEFAULT '{}',
    total_cost REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- CONTROL PLANE TASKS ---------------------------------------------------------
-- These are orchestrator-level tasks (separate from existing campaign tasks).
CREATE TABLE IF NOT EXISTS cp_tasks (
    id TEXT PRIMARY KEY,
    goal_id TEXT REFERENCES goals(id),
    assigned_agent_id TEXT REFERENCES cp_agents(id),
    title TEXT NOT NULL,
    description TEXT,
    task_type TEXT DEFAULT 'default',
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 2,
    retry_count INTEGER DEFAULT 0,
    context_json TEXT DEFAULT '{}',
    approval_status TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cp_tasks_status ON cp_tasks(status);
CREATE INDEX IF NOT EXISTS idx_cp_tasks_agent ON cp_tasks(assigned_agent_id);

-- JOBS (execution records) ----------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_jobs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES cp_tasks(id),
    agent_id TEXT NOT NULL REFERENCES cp_agents(id),
    input_json TEXT DEFAULT '{}',
    output_json TEXT DEFAULT '{}',
    cost REAL DEFAULT 0.0,
    duration_seconds REAL,
    status TEXT DEFAULT 'running',
    error_message TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cp_jobs_task ON cp_jobs(task_id);

-- APPROVALS -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_approvals (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES cp_tasks(id),
    requested_by TEXT,
    approved_by TEXT,
    status TEXT DEFAULT 'pending',
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cp_approvals_task ON cp_approvals(task_id);

-- EDGE PROJECT SNAPSHOTS -----------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_project_snapshots (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'edge',
    app_version TEXT DEFAULT '',
    snapshot_json TEXT NOT NULL,
    summary_json TEXT DEFAULT '{}',
    received_at TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cp_project_snapshots_project_machine
    ON cp_project_snapshots(project_id, machine_id);
CREATE INDEX IF NOT EXISTS idx_cp_project_snapshots_project_received
    ON cp_project_snapshots(project_id, received_at DESC);

-- EDGE COMMAND QUEUE ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_edge_commands (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    command_type TEXT NOT NULL,
    title TEXT DEFAULT '',
    created_by TEXT DEFAULT '',
    source_suggestion_id TEXT DEFAULT '',
    payload_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    result_json TEXT DEFAULT '{}',
    error_message TEXT DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dispatched_at TEXT,
    acknowledged_at TEXT,
    last_heartbeat_at TEXT,
    lease_expires_at TEXT,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cp_edge_commands_machine_status
    ON cp_edge_commands(project_id, machine_id, status, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_cp_edge_commands_project_created
    ON cp_edge_commands(project_id, created_at DESC);

-- METRICS SNAPSHOTS -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_metrics (
    id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES cp_agents(id),
    metric_name TEXT NOT NULL,
    metric_value REAL,
    recorded_at TEXT DEFAULT (datetime('now'))
);
"""
