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

-- EDGE MACHINE REGISTRY ------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_edge_machines (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'edge',
    app_version TEXT DEFAULT '',
    last_seen_at TEXT,
    last_snapshot_at TEXT,
    last_command_at TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    draining INTEGER NOT NULL DEFAULT 0,
    pause_reason TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cp_edge_machines_project_machine
    ON cp_edge_machines(project_id, machine_id);

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

-- DEPARTMENT GOVERNANCE -------------------------------------------------------
CREATE TABLE IF NOT EXISTS cp_departments (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT DEFAULT 'general',
    status TEXT NOT NULL DEFAULT 'active',
    is_system_default INTEGER NOT NULL DEFAULT 0,
    allow_store_assignment INTEGER NOT NULL DEFAULT 1,
    allow_ai_agent_execution INTEGER NOT NULL DEFAULT 1,
    allow_human_assignment INTEGER NOT NULL DEFAULT 1,
    requires_ceo_visibility_only INTEGER NOT NULL DEFAULT 0,
    execution_mode TEXT NOT NULL DEFAULT 'suggest_only',
    parent_department_id TEXT REFERENCES cp_departments(id),
    created_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    updated_at TEXT NOT NULL,
    updated_by TEXT DEFAULT '',
    deleted_at TEXT,
    deleted_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_cp_departments_status ON cp_departments(status);
CREATE INDEX IF NOT EXISTS idx_cp_departments_category ON cp_departments(category);

CREATE TABLE IF NOT EXISTS cp_permissions (
    id TEXT PRIMARY KEY,
    permission_key TEXT NOT NULL UNIQUE,
    permission_name TEXT NOT NULL,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_permissions_module ON cp_permissions(module);

CREATE TABLE IF NOT EXISTS cp_department_permissions (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES cp_departments(id),
    permission_id TEXT NOT NULL REFERENCES cp_permissions(id),
    allowed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(department_id, permission_id)
);

CREATE TABLE IF NOT EXISTS cp_store_departments (
    id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    department_id TEXT NOT NULL REFERENCES cp_departments(id),
    enabled INTEGER NOT NULL DEFAULT 1,
    locked INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0,
    custom_policy_enabled INTEGER NOT NULL DEFAULT 0,
    execution_mode TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT DEFAULT '',
    updated_by TEXT DEFAULT '',
    UNIQUE(store_id, department_id)
);
CREATE INDEX IF NOT EXISTS idx_cp_store_departments_store ON cp_store_departments(store_id);

CREATE TABLE IF NOT EXISTS cp_store_department_permissions (
    id TEXT PRIMARY KEY,
    store_department_id TEXT NOT NULL REFERENCES cp_store_departments(id),
    permission_id TEXT NOT NULL REFERENCES cp_permissions(id),
    allowed INTEGER NOT NULL DEFAULT 1,
    source TEXT NOT NULL DEFAULT 'override',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(store_department_id, permission_id)
);

CREATE TABLE IF NOT EXISTS cp_policies (
    id TEXT PRIMARY KEY,
    policy_code TEXT NOT NULL UNIQUE,
    policy_name TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    condition_json TEXT DEFAULT '{}',
    effect TEXT NOT NULL,
    approval_chain_json TEXT DEFAULT '[]',
    escalation_json TEXT DEFAULT '{}',
    audit_required INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 100,
    is_active INTEGER NOT NULL DEFAULT 1,
    effective_from TEXT,
    effective_to TEXT,
    created_by TEXT DEFAULT '',
    updated_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_policies_scope_target ON cp_policies(scope_type, target_type, target_id, is_active);

CREATE TABLE IF NOT EXISTS cp_audit_logs (
    id TEXT PRIMARY KEY,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    before_json TEXT DEFAULT '{}',
    after_json TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'success',
    reason TEXT DEFAULT '',
    store_id TEXT,
    department_id TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cp_audit_logs_created ON cp_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cp_audit_logs_resource ON cp_audit_logs(resource_type, resource_id);

CREATE TABLE IF NOT EXISTS cp_roles (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cp_role_permissions (
    id TEXT PRIMARY KEY,
    role_id TEXT NOT NULL REFERENCES cp_roles(id),
    permission_id TEXT NOT NULL REFERENCES cp_permissions(id),
    allowed INTEGER NOT NULL DEFAULT 1,
    UNIQUE(role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS cp_department_roles (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES cp_departments(id),
    role_id TEXT NOT NULL REFERENCES cp_roles(id),
    UNIQUE(department_id, role_id)
);

CREATE TABLE IF NOT EXISTS cp_ai_agents (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    department_id TEXT NOT NULL REFERENCES cp_departments(id),
    store_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    execution_mode TEXT NOT NULL DEFAULT 'suggest_only',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
