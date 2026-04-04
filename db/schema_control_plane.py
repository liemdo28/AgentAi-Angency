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

-- METRICS SNAPSHOTS -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_metrics (
    id TEXT PRIMARY KEY,
    agent_id TEXT REFERENCES cp_agents(id),
    metric_name TEXT NOT NULL,
    metric_value REAL,
    recorded_at TEXT DEFAULT (datetime('now'))
);
"""
