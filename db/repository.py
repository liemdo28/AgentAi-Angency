"""
ControlPlaneDB — repository for the orchestrator's own tables.

Uses the same SQLite WAL database as the existing agency, but operates
on the cp_* tables (and goals / cp_approvals).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from db.schema_control_plane import CONTROL_PLANE_SCHEMA

logger = logging.getLogger("db.control_plane")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "agency.db"

DEFAULT_DEPARTMENTS = [
    {"code": "CEO_OFFICE", "name": "CEO Office", "category": "leadership", "description": "Company-wide executive control", "status": "active", "requires_ceo_visibility_only": 1, "execution_mode": "semi_auto"},
    {"code": "OPERATIONS", "name": "Operations", "category": "core_business", "description": "Store execution, issue flow, and service operations", "status": "active", "execution_mode": "semi_auto"},
    {"code": "MARKETING", "name": "Marketing", "category": "core_business", "description": "Campaign, content, promotion, and CRM operations", "status": "active", "execution_mode": "semi_auto"},
    {"code": "SALES", "name": "Sales", "category": "core_business", "description": "Lead, pipeline, and conversion performance", "status": "active", "execution_mode": "suggest_only"},
    {"code": "CUSTOMER_SUPPORT", "name": "Customer Support", "category": "core_business", "description": "Tickets, SLA, and customer communication", "status": "active", "execution_mode": "suggest_only"},
    {"code": "FINANCE", "name": "Finance", "category": "core_business", "description": "Revenue, invoice, margin, and payout control", "status": "active", "execution_mode": "suggest_only"},
    {"code": "HR", "name": "HR", "category": "core_business", "description": "People operations and employee records", "status": "locked", "execution_mode": "disabled"},
    {"code": "DESIGN", "name": "Design", "category": "core_business", "description": "Creative assets, menu visuals, and brand design", "status": "active", "execution_mode": "suggest_only"},
    {"code": "ENGINEERING_IT", "name": "Engineering / IT", "category": "core_business", "description": "Systems, source, deployment, and integrations", "status": "active", "execution_mode": "semi_auto"},
    {"code": "DATA_ANALYTICS", "name": "Data / Analytics", "category": "core_business", "description": "Reporting, metrics, and data quality", "status": "active", "execution_mode": "semi_auto"},
    {"code": "REVIEW_MANAGEMENT", "name": "Review Management", "category": "core_business", "description": "Google/Yelp review ops and reply workflows", "status": "active", "execution_mode": "semi_auto"},
    {"code": "ADS_MEDIA", "name": "Ads / Media Buying", "category": "growth", "description": "Paid media management and budget optimization", "status": "active", "execution_mode": "suggest_only"},
    {"code": "SEO_CONTENT", "name": "SEO / Content", "category": "growth", "description": "Organic growth, local SEO, and content production", "status": "active", "execution_mode": "suggest_only"},
    {"code": "PROCUREMENT", "name": "Procurement / Purchasing", "category": "operations", "description": "Vendor sourcing and purchasing workflow", "status": "locked", "execution_mode": "disabled"},
    {"code": "INVENTORY_SUPPLY", "name": "Inventory / Supply", "category": "operations", "description": "Supply planning and inventory controls", "status": "active", "execution_mode": "semi_auto"},
    {"code": "COMPLIANCE_QA", "name": "Compliance / QA", "category": "operations", "description": "Audit, QA, and compliance checks", "status": "hidden", "requires_ceo_visibility_only": 1, "execution_mode": "suggest_only"},
    {"code": "AI_AUTOMATION", "name": "AI Automation", "category": "system", "description": "Cross-functional AI automations and governance", "status": "active", "execution_mode": "semi_auto"},
    {"code": "INTEGRATION_API", "name": "Integration / API", "category": "system", "description": "Integration pipelines and external service connectivity", "status": "active", "execution_mode": "semi_auto"},
    {"code": "REPORTING_BI", "name": "Reporting / BI", "category": "system", "description": "BI delivery, scorecards, and scheduled reporting", "status": "active", "execution_mode": "semi_auto"},
    {"code": "ADMIN_SUPER_ADMIN", "name": "Admin / Super Admin", "category": "system", "description": "Administrative control over the whole platform", "status": "active", "requires_ceo_visibility_only": 1, "execution_mode": "full_auto"},
]

DEFAULT_PERMISSIONS = [
    ("create_department", "Create Department", "Department Admin", "create", "Create a new department"),
    ("edit_department", "Edit Department", "Department Admin", "edit", "Update department metadata"),
    ("delete_department", "Delete Department", "Department Admin", "delete", "Soft delete a department"),
    ("hide_department", "Hide Department", "Department Admin", "hide", "Hide a department from standard visibility"),
    ("lock_department", "Lock Department", "Department Admin", "lock", "Lock department execution and assignments"),
    ("manage_store_assignment", "Manage Store Assignment", "Department Admin", "assign", "Assign departments to stores"),
    ("manage_policies", "Manage Policies", "Policy Admin", "manage", "Create and update policy rules"),
    ("view_audit_logs", "View Audit Logs", "Audit", "view", "Read governance audit logs"),
    ("override_approval", "Override Approval", "Approval", "override", "Override an approval decision"),
    ("manage_ai_agents", "Manage AI Agents", "AI Actions", "manage", "Change AI execution modes"),
    ("reviews.read", "Read Reviews", "Reviews", "view", "Read review records"),
    ("reviews.reply", "Reply to Reviews", "Reviews", "reply", "Create or publish review replies"),
    ("reviews.export", "Export Reviews", "Reviews", "export", "Export review data"),
    ("ads.read", "Read Ads", "Ads", "view", "Read ad accounts and campaigns"),
    ("ads.create", "Create Ads", "Ads", "create", "Create ad campaigns"),
    ("ads.edit", "Edit Ads", "Ads", "edit", "Edit ads and targeting"),
    ("ads.pause", "Pause Ads", "Ads", "pause", "Pause or resume campaigns"),
    ("finance.read", "Read Finance", "Finance", "view", "Read finance dashboards and reports"),
    ("invoices.export", "Export Invoices", "Finance", "export", "Export invoice and payout data"),
    ("staff.read", "Read Staff", "HR", "view", "Read HR and staff records"),
    ("staff.write", "Write Staff", "HR", "edit", "Update staff records"),
    ("menu.read", "Read Menu", "Store Ops", "view", "Read menu or operational data"),
    ("menu.write", "Write Menu", "Store Ops", "edit", "Update menu or operational data"),
    ("analytics.read", "Read Analytics", "Analytics", "view", "Read analytics dashboards"),
    ("analytics.export", "Export Analytics", "Analytics", "export", "Export analytics results"),
    ("campaigns.publish", "Publish Campaigns", "Marketing", "publish", "Publish campaigns or content live"),
    ("tasks.assign", "Assign Tasks", "Operations", "assign", "Assign work items"),
    ("policy.simulate", "Simulate Policy", "Policy Admin", "simulate", "Run dry-run policy evaluation"),
]

DEFAULT_POLICIES = [
    {
        "policy_code": "POLICY_001_REVIEW_LOW_RATING",
        "policy_name": "Negative review approval",
        "scope_type": "department",
        "target_type": "department_code",
        "target_id": "REVIEW_MANAGEMENT",
        "condition_json": {"all": [{"field": "action", "op": "eq", "value": "reviews.reply.publish"}, {"field": "rating", "op": "lte", "value": 3}]},
        "effect": "require_approval",
        "approval_chain_json": ["store_manager"],
        "escalation_json": {"target": "store_manager"},
        "audit_required": 1,
        "priority": 40,
    },
    {
        "policy_code": "POLICY_002_REVIEW_HIGH_RATING",
        "policy_name": "Positive review auto execute",
        "scope_type": "department",
        "target_type": "department_code",
        "target_id": "REVIEW_MANAGEMENT",
        "condition_json": {"all": [{"field": "action", "op": "eq", "value": "reviews.reply.publish"}, {"field": "rating", "op": "gte", "value": 4}]},
        "effect": "auto_execute",
        "approval_chain_json": [],
        "escalation_json": {},
        "audit_required": 1,
        "priority": 50,
    },
    {
        "policy_code": "POLICY_003_HIDDEN_DEPARTMENT_VISIBILITY",
        "policy_name": "Hidden department CEO visibility",
        "scope_type": "company",
        "target_type": "visibility",
        "target_id": "department.hidden",
        "condition_json": {"all": [{"field": "department_status", "op": "eq", "value": "hidden"}]},
        "effect": "ceo_only_visibility",
        "approval_chain_json": [],
        "escalation_json": {},
        "audit_required": 1,
        "priority": 20,
    },
    {
        "policy_code": "POLICY_004_LOCKED_DEPARTMENT_EXECUTION",
        "policy_name": "Locked department deny execution",
        "scope_type": "company",
        "target_type": "execution",
        "target_id": "department.locked",
        "condition_json": {"all": [{"field": "department_status", "op": "eq", "value": "locked"}]},
        "effect": "deny",
        "approval_chain_json": [],
        "escalation_json": {},
        "audit_required": 1,
        "priority": 10,
    },
    {
        "policy_code": "POLICY_005_DEPARTMENT_DELETE_PROTECTION",
        "policy_name": "Department delete requires CEO approval",
        "scope_type": "action",
        "target_type": "action",
        "target_id": "department.delete",
        "condition_json": {"all": [{"field": "action", "op": "eq", "value": "department.delete"}]},
        "effect": "require_ceo_approval",
        "approval_chain_json": ["ceo"],
        "escalation_json": {"target": "ceo"},
        "audit_required": 1,
        "priority": 5,
    },
]


class ControlPlaneDB:
    """Thin repository over the control-plane tables."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._ensure_schema()

    # ── connection helpers ────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            conn.executescript(CONTROL_PLANE_SCHEMA)
            self._ensure_edge_command_columns(conn)
            self._ensure_approval_columns(conn)
            self._seed_governance_defaults(conn)
            conn.commit()
            logger.info("Control plane schema ready (%s)", self.db_path)
        finally:
            conn.close()

    def _decode_json(self, value: str | None) -> dict:
        try:
            return json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}

    def _hydrate_edge_command(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        item = dict(row)
        item["payload"] = self._decode_json(item.get("payload_json"))
        item["result"] = self._decode_json(item.get("result_json"))
        return item

    def _hydrate_edge_machine(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        item = dict(row)
        item["paused"] = bool(item.get("paused"))
        item["draining"] = bool(item.get("draining"))
        return item

    def _ensure_edge_command_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(cp_edge_commands)").fetchall()
        }
        required = {
            "attempt_count": "ALTER TABLE cp_edge_commands ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "ALTER TABLE cp_edge_commands ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
            "acknowledged_at": "ALTER TABLE cp_edge_commands ADD COLUMN acknowledged_at TEXT",
            "last_heartbeat_at": "ALTER TABLE cp_edge_commands ADD COLUMN last_heartbeat_at TEXT",
            "lease_expires_at": "ALTER TABLE cp_edge_commands ADD COLUMN lease_expires_at TEXT",
        }
        for column, statement in required.items():
            if column not in existing:
                conn.execute(statement)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_cp_edge_commands_project_lease
                ON cp_edge_commands(project_id, machine_id, lease_expires_at)
            """
        )

    def _ensure_approval_columns(self, conn: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(cp_approvals)").fetchall()
        }
        required = {
            "resource_type": "ALTER TABLE cp_approvals ADD COLUMN resource_type TEXT DEFAULT 'task'",
            "resource_id": "ALTER TABLE cp_approvals ADD COLUMN resource_id TEXT DEFAULT ''",
            "approval_level": "ALTER TABLE cp_approvals ADD COLUMN approval_level TEXT DEFAULT 'supervisor'",
            "policy_code": "ALTER TABLE cp_approvals ADD COLUMN policy_code TEXT DEFAULT ''",
            "store_id": "ALTER TABLE cp_approvals ADD COLUMN store_id TEXT",
            "department_id": "ALTER TABLE cp_approvals ADD COLUMN department_id TEXT",
            "request_json": "ALTER TABLE cp_approvals ADD COLUMN request_json TEXT DEFAULT '{}'",
            "decision_json": "ALTER TABLE cp_approvals ADD COLUMN decision_json TEXT DEFAULT '{}'",
            "expires_at": "ALTER TABLE cp_approvals ADD COLUMN expires_at TEXT",
        }
        for column, statement in required.items():
            if column not in existing:
                conn.execute(statement)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _decode_json_list(self, value: str | None) -> list:
        try:
            parsed = json.loads(value or "[]")
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def _bool(self, value: Any) -> bool:
        return bool(int(value)) if isinstance(value, (int, bool)) else str(value).lower() in {"1", "true", "yes"}

    def _seed_governance_defaults(self, conn: sqlite3.Connection) -> None:
        now = self._now()
        for code, name, module, action, description in DEFAULT_PERMISSIONS:
            conn.execute(
                """
                INSERT OR IGNORE INTO cp_permissions (
                    id, permission_key, permission_name, module, action, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid4()), code, name, module, action, description, now),
            )

        for item in DEFAULT_DEPARTMENTS:
            conn.execute(
                """
                INSERT OR IGNORE INTO cp_departments (
                    id, code, name, description, category, status, is_system_default,
                    allow_store_assignment, allow_ai_agent_execution, allow_human_assignment,
                    requires_ceo_visibility_only, execution_mode, created_at, created_by, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, 'system', ?, 'system')
                """,
                (
                    str(uuid4()),
                    item["code"],
                    item["name"],
                    item.get("description", ""),
                    item.get("category", "general"),
                    item.get("status", "active"),
                    item.get("allow_store_assignment", 1),
                    item.get("allow_ai_agent_execution", 1),
                    item.get("allow_human_assignment", 1),
                    item.get("requires_ceo_visibility_only", 0),
                    item.get("execution_mode", "suggest_only"),
                    now,
                    now,
                ),
            )

        for item in DEFAULT_POLICIES:
            conn.execute(
                """
                INSERT OR IGNORE INTO cp_policies (
                    id, policy_code, policy_name, scope_type, target_type, target_id,
                    condition_json, effect, approval_chain_json, escalation_json,
                    audit_required, priority, is_active, created_by, updated_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'system', 'system', ?, ?)
                """,
                (
                    str(uuid4()),
                    item["policy_code"],
                    item["policy_name"],
                    item["scope_type"],
                    item["target_type"],
                    item["target_id"],
                    json.dumps(item.get("condition_json") or {}, ensure_ascii=False),
                    item["effect"],
                    json.dumps(item.get("approval_chain_json") or [], ensure_ascii=False),
                    json.dumps(item.get("escalation_json") or {}, ensure_ascii=False),
                    item.get("audit_required", 1),
                    item.get("priority", 100),
                    now,
                    now,
                ),
            )
            policy_row = conn.execute(
                "SELECT id, policy_code, policy_name, scope_type, target_type, target_id, condition_json, effect, approval_chain_json, escalation_json, audit_required, priority, is_active, effective_from, effective_to, created_by, updated_by, created_at, updated_at FROM cp_policies WHERE policy_code = ?",
                (item["policy_code"],),
            ).fetchone()
            if policy_row:
                version_exists = conn.execute(
                    "SELECT 1 FROM cp_policy_versions WHERE policy_id = ? LIMIT 1",
                    (policy_row["id"],),
                ).fetchone()
                if not version_exists:
                    self._create_policy_version(
                        conn,
                        policy_id=policy_row["id"],
                        snapshot=self._hydrate_policy(policy_row) or {},
                        created_by="system",
                        change_note="Seeded default policy",
                    )

    def _hydrate_department(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        item = dict(row)
        for key in (
            "is_system_default",
            "allow_store_assignment",
            "allow_ai_agent_execution",
            "allow_human_assignment",
            "requires_ceo_visibility_only",
        ):
            item[key] = self._bool(item.get(key))
        item["is_active"] = item.get("status") == "active"
        item["is_locked"] = item.get("status") == "locked"
        item["is_hidden"] = item.get("status") == "hidden"
        item["is_deleted"] = item.get("status") == "deleted"
        return item

    def _hydrate_permission(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        return dict(row)

    def _hydrate_policy(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        item = dict(row)
        item["condition"] = self._decode_json(item.get("condition_json"))
        item["approval_chain"] = self._decode_json_list(item.get("approval_chain_json"))
        item["escalation"] = self._decode_json(item.get("escalation_json"))
        item["audit_required"] = self._bool(item.get("audit_required"))
        item["is_active"] = self._bool(item.get("is_active"))
        return item

    def _hydrate_audit_log(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        item = dict(row)
        item["before"] = self._decode_json(item.get("before_json"))
        item["after"] = self._decode_json(item.get("after_json"))
        return item

    def _hydrate_approval(self, row: sqlite3.Row | None) -> Optional[dict]:
        if not row:
            return None
        item = dict(row)
        item["request"] = self._decode_json(item.get("request_json"))
        item["decision"] = self._decode_json(item.get("decision_json"))
        return item

    def _department_permission_map(self, conn: sqlite3.Connection, department_id: str) -> dict[str, bool]:
        rows = conn.execute(
            """
            SELECT p.permission_key, dp.allowed
            FROM cp_department_permissions dp
            JOIN cp_permissions p ON p.id = dp.permission_id
            WHERE dp.department_id = ?
            """,
            (department_id,),
        ).fetchall()
        return {row["permission_key"]: self._bool(row["allowed"]) for row in rows}

    def _store_department_assignment(self, conn: sqlite3.Connection, store_id: str, department_id: str) -> Optional[dict]:
        row = conn.execute(
            "SELECT * FROM cp_store_departments WHERE store_id = ? AND department_id = ?",
            (store_id, department_id),
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        for key in ("enabled", "locked", "hidden", "deleted", "custom_policy_enabled"):
            item[key] = self._bool(item.get(key))
        return item

    def _store_permission_overrides(self, conn: sqlite3.Connection, store_department_id: str) -> dict[str, bool]:
        rows = conn.execute(
            """
            SELECT p.permission_key, sdp.allowed
            FROM cp_store_department_permissions sdp
            JOIN cp_permissions p ON p.id = sdp.permission_id
            WHERE sdp.store_department_id = ?
            """,
            (store_department_id,),
        ).fetchall()
        return {row["permission_key"]: self._bool(row["allowed"]) for row in rows}

    def _effective_permission(self, conn: sqlite3.Connection, department_id: str, permission_key: str, store_id: str | None = None) -> bool:
        base = self._department_permission_map(conn, department_id).get(permission_key, False)
        if not store_id:
            return base
        assignment = self._store_department_assignment(conn, store_id, department_id)
        if not assignment:
            return base
        overrides = self._store_permission_overrides(conn, assignment["id"])
        if permission_key in overrides:
            return overrides[permission_key]
        return base

    def _match_condition(self, context: dict, condition: dict | list | None) -> bool:
        if not condition:
            return True
        if isinstance(condition, list):
            return all(self._match_condition(context, item) for item in condition)
        if "all" in condition:
            return all(self._match_condition(context, item) for item in condition.get("all", []))
        if "any" in condition:
            return any(self._match_condition(context, item) for item in condition.get("any", []))
        field = condition.get("field")
        op = condition.get("op", "eq")
        expected = condition.get("value")
        actual = context.get(field)
        if op == "eq":
            return actual == expected
        if op == "neq":
            return actual != expected
        if op == "lte":
            return actual is not None and actual <= expected
        if op == "gte":
            return actual is not None and actual >= expected
        if op == "lt":
            return actual is not None and actual < expected
        if op == "gt":
            return actual is not None and actual > expected
        if op == "in":
            return actual in (expected or [])
        if op == "contains":
            return actual is not None and expected in actual
        return False

    def _log_audit(
        self,
        conn: sqlite3.Connection,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before: dict | None = None,
        after: dict | None = None,
        status: str = "success",
        reason: str = "",
        store_id: str | None = None,
        department_id: str | None = None,
    ) -> dict:
        audit = {
            "id": str(uuid4()),
            "actor_type": actor_type,
            "actor_id": actor_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before_json": json.dumps(before or {}, ensure_ascii=False),
            "after_json": json.dumps(after or {}, ensure_ascii=False),
            "status": status,
            "reason": reason,
            "store_id": store_id,
            "department_id": department_id,
            "created_at": self._now(),
        }
        conn.execute(
            """
            INSERT INTO cp_audit_logs (
                id, actor_type, actor_id, action, resource_type, resource_id, before_json, after_json,
                status, reason, store_id, department_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit["id"],
                audit["actor_type"],
                audit["actor_id"],
                audit["action"],
                audit["resource_type"],
                audit["resource_id"],
                audit["before_json"],
                audit["after_json"],
                audit["status"],
                audit["reason"],
                audit["store_id"],
                audit["department_id"],
                audit["created_at"],
            ),
        )
        return audit

    def _upsert_edge_machine(
        self,
        conn: sqlite3.Connection,
        *,
        project_id: str,
        machine_id: str,
        machine_name: str,
        source_type: str = "edge",
        app_version: str = "",
        last_seen_at: str | None = None,
        last_snapshot_at: str | None = None,
        last_command_at: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        machine_row_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO cp_edge_machines (
                id,
                project_id,
                machine_id,
                machine_name,
                source_type,
                app_version,
                last_seen_at,
                last_snapshot_at,
                last_command_at,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, machine_id) DO UPDATE SET
                machine_name = excluded.machine_name,
                source_type = excluded.source_type,
                app_version = excluded.app_version,
                last_seen_at = COALESCE(excluded.last_seen_at, cp_edge_machines.last_seen_at),
                last_snapshot_at = COALESCE(excluded.last_snapshot_at, cp_edge_machines.last_snapshot_at),
                last_command_at = COALESCE(excluded.last_command_at, cp_edge_machines.last_command_at),
                updated_at = excluded.updated_at
            """,
            (
                machine_row_id,
                project_id,
                machine_id,
                machine_name,
                source_type,
                app_version,
                last_seen_at,
                last_snapshot_at,
                last_command_at,
                now,
                now,
            ),
        )

    def _ensure_task_stub(self, conn: sqlite3.Connection, task_id: str, title: str, description: str = "") -> None:
        existing = conn.execute("SELECT id FROM cp_tasks WHERE id = ?", (task_id,)).fetchone()
        if existing:
            return
        agent_row = conn.execute("SELECT id FROM cp_agents ORDER BY created_at ASC LIMIT 1").fetchone()
        if not agent_row:
            conn.execute(
                """
                INSERT OR IGNORE INTO cp_agents (id, role, agent_type, model, budget_limit, status, config_json, total_cost, created_at)
                VALUES ('workflow', 'Workflow', 'system', '', 50.0, 'active', '{}', 0.0, ?)
                """,
                (self._now(),),
            )
            assigned_agent_id = "workflow"
        else:
            assigned_agent_id = agent_row["id"]
        conn.execute(
            """
            INSERT INTO cp_tasks (
                id, goal_id, assigned_agent_id, title, description, task_type,
                status, priority, retry_count, context_json, approval_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'governance_action', 'pending', 2, 0, '{}', 'pending', ?, ?)
            """,
            (task_id, None, assigned_agent_id, title, description, self._now(), self._now()),
        )

    def _ensure_default_agent(self, conn: sqlite3.Connection, agent_id: str = "workflow") -> None:
        existing = conn.execute("SELECT id FROM cp_agents WHERE id = ?", (agent_id,)).fetchone()
        if existing:
            return
        conn.execute(
            """
            INSERT OR IGNORE INTO cp_agents (id, role, agent_type, model, budget_limit, status, config_json, total_cost, created_at)
            VALUES (?, 'Workflow', 'system', '', 50.0, 'active', '{}', 0.0, ?)
            """,
            (agent_id, self._now()),
        )

    # ── goals ─────────────────────────────────────────────────────────

    def create_goal(self, title: str, description: str = "", owner: str = "") -> dict:
        gid = str(uuid4())
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO goals (id, title, description, owner) VALUES (?, ?, ?, ?)",
                (gid, title, description, owner),
            )
            conn.commit()
            return {"id": gid, "title": title}
        finally:
            conn.close()

    def list_goals(self) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── agents ────────────────────────────────────────────────────────

    def register_agent(self, agent_id: str, role: str, agent_type: str,
                       model: str = "", budget_limit: float = 50.0) -> dict:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO cp_agents
                   (id, role, agent_type, model, budget_limit)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_id, role, agent_type, model, budget_limit),
            )
            conn.commit()
            return {"id": agent_id, "role": role}
        finally:
            conn.close()

    def list_agents(self) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM cp_agents ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_agent(self, agent_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cp_agents WHERE id = ?", (agent_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── tasks ─────────────────────────────────────────────────────────

    def create_task(self, title: str, assigned_agent_id: str,
                    goal_id: str = "", description: str = "",
                    task_type: str = "default", priority: int = 2,
                    context_json: dict | None = None) -> dict:
        tid = str(uuid4())
        conn = self._conn()
        try:
            self._ensure_default_agent(conn, assigned_agent_id)
            conn.execute(
                """INSERT INTO cp_tasks
                   (id, goal_id, assigned_agent_id, title, description,
                    task_type, priority, context_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tid, goal_id or None, assigned_agent_id, title, description,
                 task_type, priority, json.dumps(context_json or {})),
            )
            conn.commit()
            return {"id": tid, "title": title, "status": "pending"}
        finally:
            conn.close()

    def get_pending_tasks(self) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM cp_tasks WHERE status = 'pending' ORDER BY priority DESC, created_at ASC"
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["context_json"] = json.loads(d.get("context_json") or "{}")
                results.append(d)
            return results
        finally:
            conn.close()

    def list_tasks(self, status: str | None = None, limit: int = 100) -> List[dict]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM cp_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_task(self, task_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cp_tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                d = dict(row)
                d["context_json"] = json.loads(d.get("context_json") or "{}")
                return d
            return None
        finally:
            conn.close()

    def update_task_status(self, task_id: str, status: str) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            extras = ""
            if status == "running":
                extras = ", started_at = ?"
            elif status in ("success", "failed", "cancelled"):
                extras = ", completed_at = ?"

            if extras:
                conn.execute(
                    f"UPDATE cp_tasks SET status = ?, updated_at = ?{extras} WHERE id = ?",
                    (status, now, now, task_id) if extras else (status, now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE cp_tasks SET status = ? WHERE id = ?",
                    (status, task_id),
                )
            conn.commit()
        finally:
            conn.close()

    def retry_task(self, task_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE cp_tasks SET status = 'pending', retry_count = retry_count + 1 WHERE id = ?",
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ── jobs ──────────────────────────────────────────────────────────

    def save_job(self, task_id: str, agent_id: str,
                 input_data: dict, output_data: dict,
                 started_at: str = "", cost: float = 0.0) -> dict:
        jid = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO cp_jobs
                   (id, task_id, agent_id, input_json, output_json,
                    cost, status, started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'success', ?, ?)""",
                (jid, task_id, agent_id,
                 json.dumps(input_data), json.dumps(output_data),
                 cost, started_at or now, now),
            )
            conn.commit()
            return {"id": jid, "task_id": task_id}
        finally:
            conn.close()

    def list_jobs(self, task_id: str | None = None, limit: int = 50) -> List[dict]:
        conn = self._conn()
        try:
            if task_id:
                rows = conn.execute(
                    "SELECT * FROM cp_jobs WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_jobs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── approvals ─────────────────────────────────────────────────────

    def request_approval(
        self,
        task_id: str,
        requested_by: str = "system",
        *,
        resource_type: str = "task",
        resource_id: str | None = None,
        approval_level: str = "supervisor",
        policy_code: str = "",
        store_id: str | None = None,
        department_id: str | None = None,
        request_payload: dict | None = None,
        expires_at: str | None = None,
    ) -> dict:
        aid = str(uuid4())
        now = self._now()
        conn = self._conn()
        try:
            self._ensure_task_stub(
                conn,
                task_id,
                title=f"Approval required: {resource_type}",
                description=f"Governance approval placeholder for {resource_id or task_id}",
            )
            conn.execute(
                """
                INSERT INTO cp_approvals (
                    id, task_id, requested_by, status, created_at,
                    resource_type, resource_id, approval_level, policy_code,
                    store_id, department_id, request_json, decision_json, expires_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)
                """,
                (
                    aid,
                    task_id,
                    requested_by,
                    now,
                    resource_type,
                    resource_id or task_id,
                    approval_level,
                    policy_code,
                    store_id,
                    department_id,
                    json.dumps(request_payload or {}, ensure_ascii=False),
                    expires_at,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM cp_approvals WHERE id = ?", (aid,)).fetchone()
            return self._hydrate_approval(row) or {"id": aid, "task_id": task_id, "status": "pending"}
        finally:
            conn.close()

    def resolve_approval(self, approval_id: str, status: str,
                         approved_by: str = "", reason: str = "", decision_payload: dict | None = None) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE cp_approvals
                   SET status = ?, approved_by = ?, reason = ?, resolved_at = ?, decision_json = ?
                   WHERE id = ?""",
                (status, approved_by, reason, now, json.dumps(decision_payload or {}, ensure_ascii=False), approval_id),
            )
            # Also update the task's approval_status
            row = conn.execute(
                "SELECT task_id FROM cp_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE cp_tasks SET approval_status = ? WHERE id = ?",
                    (status, row["task_id"]),
                )
            conn.commit()
            refreshed = conn.execute("SELECT * FROM cp_approvals WHERE id = ?", (approval_id,)).fetchone()
            approval = self._hydrate_approval(refreshed)
            if approval and status == "approved" and approval.get("resource_type") == "department_action":
                execution = self.execute_governance_approval(approval_id, actor_id=approved_by or "system")
                approval = self._hydrate_approval(conn.execute("SELECT * FROM cp_approvals WHERE id = ?", (approval_id,)).fetchone())
                if approval is not None:
                    approval["execution"] = execution
            return approval
        finally:
            conn.close()

    def list_approvals(self, status: str = "pending", resource_type: str | None = None) -> List[dict]:
        conn = self._conn()
        try:
            if resource_type:
                rows = conn.execute(
                    "SELECT * FROM cp_approvals WHERE status = ? AND resource_type = ? ORDER BY created_at DESC",
                    (status, resource_type),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_approvals WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            return [item for item in (self._hydrate_approval(r) for r in rows) if item]
        finally:
            conn.close()

    # ── edge project snapshots ───────────────────────────────────────

    def upsert_project_snapshot(
        self,
        *,
        project_id: str,
        machine_id: str,
        machine_name: str,
        source_type: str,
        snapshot: dict,
        app_version: str = "",
        received_at: str | None = None,
    ) -> dict:
        snapshot_json = json.dumps(snapshot or {}, ensure_ascii=False)
        summary_json = json.dumps((snapshot or {}).get("summary") or {}, ensure_ascii=False)
        now = received_at or datetime.now(timezone.utc).isoformat()
        row_id = str(uuid4())
        conn = self._conn()
        try:
            self._upsert_edge_machine(
                conn,
                project_id=project_id,
                machine_id=machine_id,
                machine_name=machine_name,
                source_type=source_type,
                app_version=app_version,
                last_seen_at=now,
                last_snapshot_at=now,
            )
            conn.execute(
                """
                INSERT INTO cp_project_snapshots (
                    id,
                    project_id,
                    machine_id,
                    machine_name,
                    source_type,
                    app_version,
                    snapshot_json,
                    summary_json,
                    received_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, machine_id) DO UPDATE SET
                    machine_name = excluded.machine_name,
                    source_type = excluded.source_type,
                    app_version = excluded.app_version,
                    snapshot_json = excluded.snapshot_json,
                    summary_json = excluded.summary_json,
                    received_at = excluded.received_at,
                    updated_at = excluded.updated_at
                """,
                (
                    row_id,
                    project_id,
                    machine_id,
                    machine_name,
                    source_type,
                    app_version,
                    snapshot_json,
                    summary_json,
                    now,
                    now,
                ),
            )
            conn.commit()
            return {
                "project_id": project_id,
                "machine_id": machine_id,
                "machine_name": machine_name,
                "source_type": source_type,
                "app_version": app_version,
                "received_at": now,
            }
        finally:
            conn.close()

    def list_project_snapshots(self, project_id: str) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM cp_project_snapshots
                WHERE project_id = ?
                ORDER BY received_at DESC, updated_at DESC
                """,
                (project_id,),
            ).fetchall()
            results: list[dict] = []
            for row in rows:
                item = dict(row)
                try:
                    item["snapshot"] = json.loads(item.get("snapshot_json") or "{}")
                except json.JSONDecodeError:
                    item["snapshot"] = {}
                try:
                    item["summary"] = json.loads(item.get("summary_json") or "{}")
                except json.JSONDecodeError:
                    item["summary"] = {}
                results.append(item)
            return results
        finally:
            conn.close()

    def get_latest_project_snapshot(self, project_id: str) -> Optional[dict]:
        snapshots = self.list_project_snapshots(project_id)
        return snapshots[0] if snapshots else None

    def create_edge_command(
        self,
        *,
        project_id: str,
        machine_id: str,
        machine_name: str,
        command_type: str,
        payload: dict | None = None,
        title: str = "",
        created_by: str = "",
        source_suggestion_id: str = "",
        max_attempts: int = 3,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        command_id = str(uuid4())
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO cp_edge_commands (
                    id,
                    project_id,
                    machine_id,
                    machine_name,
                    command_type,
                    title,
                    created_by,
                    source_suggestion_id,
                    payload_json,
                    status,
                    result_json,
                    error_message,
                    attempt_count,
                    max_attempts,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '{}', '', 0, ?, ?, ?)
                """,
                (
                    command_id,
                    project_id,
                    machine_id,
                    machine_name,
                    command_type,
                    title,
                    created_by,
                    source_suggestion_id,
                    json.dumps(payload or {}, ensure_ascii=False),
                    max_attempts,
                    now,
                    now,
                ),
            )
            conn.commit()
            return {
                "id": command_id,
                "project_id": project_id,
                "machine_id": machine_id,
                "machine_name": machine_name,
                "command_type": command_type,
                "status": "pending",
                "title": title,
                "attempt_count": 0,
                "max_attempts": max_attempts,
                "created_at": now,
            }
        finally:
            conn.close()

    def list_edge_machines(self, project_id: str) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT *
                FROM cp_edge_machines
                WHERE project_id = ?
                ORDER BY machine_name ASC, machine_id ASC
                """,
                (project_id,),
            ).fetchall()
            return [item for item in (self._hydrate_edge_machine(row) for row in rows) if item]
        finally:
            conn.close()

    def get_edge_machine(self, *, project_id: str, machine_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT *
                FROM cp_edge_machines
                WHERE project_id = ? AND machine_id = ?
                """,
                (project_id, machine_id),
            ).fetchone()
            return self._hydrate_edge_machine(row)
        finally:
            conn.close()

    def set_edge_machine_control(
        self,
        *,
        project_id: str,
        machine_id: str,
        paused: bool | None = None,
        draining: bool | None = None,
        pause_reason: str | None = None,
    ) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM cp_edge_machines WHERE project_id = ? AND machine_id = ?",
                (project_id, machine_id),
            ).fetchone()
            if not row:
                return None
            current = dict(row)
            next_paused = int(current["paused"] if paused is None else paused)
            next_draining = int(current["draining"] if draining is None else draining)
            next_reason = current.get("pause_reason", "")
            if pause_reason is not None:
                next_reason = pause_reason
            elif not next_paused:
                next_reason = ""
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE cp_edge_machines
                SET paused = ?, draining = ?, pause_reason = ?, updated_at = ?
                WHERE project_id = ? AND machine_id = ?
                """,
                (next_paused, next_draining, next_reason, now, project_id, machine_id),
            )
            conn.commit()
            refreshed = conn.execute(
                "SELECT * FROM cp_edge_machines WHERE project_id = ? AND machine_id = ?",
                (project_id, machine_id),
            ).fetchone()
            return self._hydrate_edge_machine(refreshed)
        finally:
            conn.close()

    def cancel_pending_edge_commands(self, *, project_id: str, machine_id: str, reason: str = "Queue drained by operator.") -> int:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            cursor = conn.execute(
                """
                UPDATE cp_edge_commands
                SET status = 'cancelled',
                    error_message = ?,
                    completed_at = ?,
                    updated_at = ?,
                    lease_expires_at = NULL,
                    last_heartbeat_at = NULL
                WHERE project_id = ? AND machine_id = ? AND status = 'pending'
                """,
                (reason, now, now, project_id, machine_id),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def list_edge_commands(
        self,
        *,
        project_id: str,
        machine_id: str | None = None,
        limit: int = 20,
    ) -> List[dict]:
        conn = self._conn()
        try:
            if machine_id:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM cp_edge_commands
                    WHERE project_id = ? AND machine_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (project_id, machine_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM cp_edge_commands
                    WHERE project_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (project_id, limit),
                ).fetchall()
            return [item for item in (self._hydrate_edge_command(row) for row in rows) if item]
        finally:
            conn.close()

    def _expire_stale_edge_commands(self, conn: sqlite3.Connection, *, project_id: str, machine_id: str, now: str) -> None:
        conn.execute(
            """
            UPDATE cp_edge_commands
            SET
                status = CASE
                    WHEN attempt_count >= max_attempts THEN 'failed'
                    ELSE 'pending'
                END,
                error_message = CASE
                    WHEN attempt_count >= max_attempts THEN 'Lease expired and retry budget exhausted.'
                    ELSE 'Lease expired; command re-queued.'
                END,
                lease_expires_at = NULL,
                last_heartbeat_at = NULL,
                updated_at = ?,
                completed_at = CASE
                    WHEN attempt_count >= max_attempts THEN ?
                    ELSE completed_at
                END
            WHERE project_id = ?
              AND machine_id = ?
              AND status IN ('dispatched', 'running')
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at < ?
            """,
            (now, now, project_id, machine_id, now),
        )

    def dispatch_next_edge_command(
        self,
        *,
        project_id: str,
        machine_id: str,
        lease_seconds: int = 120,
        dispatch_grace_seconds: int = 30,
    ) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        now_dt = datetime.now(timezone.utc)
        lease_expires_at = (now_dt.timestamp() + lease_seconds)
        dispatch_grace_cutoff = datetime.fromtimestamp(
            now_dt.timestamp() - dispatch_grace_seconds,
            tz=timezone.utc,
        ).isoformat()
        conn = self._conn()
        try:
            machine = conn.execute(
                "SELECT paused, draining FROM cp_edge_machines WHERE project_id = ? AND machine_id = ?",
                (project_id, machine_id),
            ).fetchone()
            if machine and (machine["paused"] or machine["draining"]):
                return None
            self._expire_stale_edge_commands(conn, project_id=project_id, machine_id=machine_id, now=now)
            conn.commit()
            row = conn.execute(
                """
                SELECT *
                FROM cp_edge_commands
                WHERE project_id = ?
                  AND machine_id = ?
                  AND (
                    status = 'pending'
                    OR (status = 'dispatched' AND (lease_expires_at IS NULL OR lease_expires_at < ? OR dispatched_at < ?))
                  )
                  AND attempt_count < max_attempts
                ORDER BY created_at ASC, updated_at ASC
                LIMIT 1
                """,
                (project_id, machine_id, now, dispatch_grace_cutoff),
            ).fetchone()
            if not row:
                return None
            command_id = row["id"]
            conn.execute(
                """
                UPDATE cp_edge_commands
                SET
                    status = 'dispatched',
                    dispatched_at = ?,
                    updated_at = ?,
                    lease_expires_at = ?,
                    attempt_count = attempt_count + 1
                WHERE id = ?
                """,
                (now, now, datetime.fromtimestamp(lease_expires_at, tz=timezone.utc).isoformat(), command_id),
            )
            self._upsert_edge_machine(
                conn,
                project_id=project_id,
                machine_id=machine_id,
                machine_name=row["machine_name"],
                last_seen_at=now,
                last_command_at=now,
            )
            conn.commit()
            refreshed = conn.execute("SELECT * FROM cp_edge_commands WHERE id = ?", (command_id,)).fetchone()
            return self._hydrate_edge_command(refreshed)
        finally:
            conn.close()

    def acknowledge_edge_command(self, *, command_id: str, heartbeat_seconds: int = 120) -> Optional[dict]:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_expires_at = datetime.fromtimestamp(now_dt.timestamp() + heartbeat_seconds, tz=timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                UPDATE cp_edge_commands
                SET status = 'running',
                    acknowledged_at = COALESCE(acknowledged_at, ?),
                    last_heartbeat_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE id = ? AND status IN ('dispatched', 'running')
                """,
                (now, now, lease_expires_at, now, command_id),
            )
            row = conn.execute("SELECT * FROM cp_edge_commands WHERE id = ?", (command_id,)).fetchone()
            if row:
                self._upsert_edge_machine(
                    conn,
                    project_id=row["project_id"],
                    machine_id=row["machine_id"],
                    machine_name=row["machine_name"],
                    last_seen_at=now,
                    last_command_at=now,
                )
            conn.commit()
            return self._hydrate_edge_command(row)
        finally:
            conn.close()

    def heartbeat_edge_command(self, *, command_id: str, heartbeat_seconds: int = 120) -> Optional[dict]:
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        lease_expires_at = datetime.fromtimestamp(now_dt.timestamp() + heartbeat_seconds, tz=timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                UPDATE cp_edge_commands
                SET last_heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
                WHERE id = ? AND status = 'running'
                """,
                (now, lease_expires_at, now, command_id),
            )
            row = conn.execute("SELECT * FROM cp_edge_commands WHERE id = ?", (command_id,)).fetchone()
            if row:
                self._upsert_edge_machine(
                    conn,
                    project_id=row["project_id"],
                    machine_id=row["machine_id"],
                    machine_name=row["machine_name"],
                    last_seen_at=now,
                    last_command_at=now,
                )
            conn.commit()
            return self._hydrate_edge_command(row)
        finally:
            conn.close()

    def complete_edge_command(
        self,
        *,
        command_id: str,
        status: str,
        result: dict | None = None,
        error_message: str = "",
    ) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """
                UPDATE cp_edge_commands
                SET status = ?, result_json = ?, error_message = ?, completed_at = ?, updated_at = ?,
                    lease_expires_at = NULL, last_heartbeat_at = NULL
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps(result or {}, ensure_ascii=False),
                    error_message,
                    now,
                    now,
                    command_id,
                ),
            )
            row = conn.execute("SELECT * FROM cp_edge_commands WHERE id = ?", (command_id,)).fetchone()
            if row:
                self._upsert_edge_machine(
                    conn,
                    project_id=row["project_id"],
                    machine_id=row["machine_id"],
                    machine_name=row["machine_name"],
                    last_seen_at=now,
                    last_command_at=now,
                )
            conn.commit()
            return self._hydrate_edge_command(row)
        finally:
            conn.close()

    # ── department governance ───────────────────────────────────────

    def list_permissions(self, module: str | None = None) -> List[dict]:
        conn = self._conn()
        try:
            if module:
                rows = conn.execute(
                    "SELECT * FROM cp_permissions WHERE module = ? ORDER BY module, permission_key",
                    (module,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_permissions ORDER BY module, permission_key"
                ).fetchall()
            return [item for item in (self._hydrate_permission(row) for row in rows) if item]
        finally:
            conn.close()

    def list_departments(
        self,
        *,
        status: str | None = None,
        visibility: str | None = None,
        search: str | None = None,
        category: str | None = None,
        actor_role: str = "ceo",
    ) -> List[dict]:
        conditions = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if search:
            conditions.append("(name LIKE ? OR code LIKE ? OR description LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if visibility == "hidden":
            conditions.append("status = 'hidden'")
        elif visibility == "public":
            conditions.append("status != 'hidden'")
        if actor_role not in {"ceo", "super_admin"}:
            conditions.extend([
                "requires_ceo_visibility_only = 0",
                "status != 'hidden'",
                "status != 'deleted'",
            ])
        sql = "SELECT * FROM cp_departments"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY CASE status WHEN 'active' THEN 1 WHEN 'locked' THEN 2 WHEN 'hidden' THEN 3 WHEN 'deleted' THEN 4 ELSE 5 END, name ASC"

        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            results = []
            for row in rows:
                item = self._hydrate_department(row)
                if not item:
                    continue
                item["assigned_stores_count"] = conn.execute(
                    "SELECT COUNT(*) AS c FROM cp_store_departments WHERE department_id = ? AND deleted = 0",
                    (item["id"],),
                ).fetchone()["c"]
                results.append(item)
            return results
        finally:
            conn.close()

    def get_department(self, department_id: str, *, actor_role: str = "ceo") -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cp_departments WHERE id = ?", (department_id,)).fetchone()
            item = self._hydrate_department(row)
            if not item:
                return None
            if item["requires_ceo_visibility_only"] and actor_role not in {"ceo", "super_admin"}:
                return None
            item["permissions"] = self.list_department_permissions(department_id)
            item["assigned_stores_count"] = conn.execute(
                "SELECT COUNT(*) AS c FROM cp_store_departments WHERE department_id = ? AND deleted = 0",
                (department_id,),
            ).fetchone()["c"]
            return item
        finally:
            conn.close()

    def count_active_store_assignments(self, department_id: str) -> int:
        conn = self._conn()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM cp_store_departments
                WHERE department_id = ? AND enabled = 1 AND deleted = 0
                """,
                (department_id,),
            ).fetchone()
            return row["c"] if row else 0
        finally:
            conn.close()

    def create_department(self, payload: dict, *, actor_id: str = "ceo", actor_type: str = "human") -> dict:
        now = self._now()
        department_id = str(uuid4())
        status = payload.get("status", "active")
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO cp_departments (
                    id, code, name, description, category, status, is_system_default,
                    allow_store_assignment, allow_ai_agent_execution, allow_human_assignment,
                    requires_ceo_visibility_only, execution_mode, parent_department_id,
                    created_at, created_by, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    department_id,
                    payload["code"].strip().upper(),
                    payload["name"].strip(),
                    payload.get("description", "").strip(),
                    payload.get("category", "general"),
                    status,
                    int(bool(payload.get("allow_store_assignment", True))),
                    int(bool(payload.get("allow_ai_agent_execution", True))),
                    int(bool(payload.get("allow_human_assignment", True))),
                    int(bool(payload.get("requires_ceo_visibility_only", status == "hidden"))),
                    payload.get("execution_mode", "suggest_only"),
                    payload.get("parent_department_id"),
                    now,
                    actor_id,
                    now,
                    actor_id,
                ),
            )
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="department.create",
                resource_type="department",
                resource_id=department_id,
                after={"code": payload["code"].strip().upper(), "name": payload["name"].strip(), "status": status},
                department_id=department_id,
            )
            conn.commit()
            return self.get_department(department_id) or {"id": department_id}
        finally:
            conn.close()

    def update_department(self, department_id: str, payload: dict, *, actor_id: str = "ceo", actor_type: str = "human") -> Optional[dict]:
        conn = self._conn()
        try:
            before = self.get_department(department_id)
            if not before:
                return None
            status = payload.get("status", before["status"])
            deleted_at = self._now() if status == "deleted" and not before.get("deleted_at") else None
            conn.execute(
                """
                UPDATE cp_departments
                SET code = ?, name = ?, description = ?, category = ?, status = ?,
                    allow_store_assignment = ?, allow_ai_agent_execution = ?, allow_human_assignment = ?,
                    requires_ceo_visibility_only = ?, execution_mode = ?, parent_department_id = ?,
                    updated_at = ?, updated_by = ?,
                    deleted_at = CASE WHEN ? = 'deleted' THEN COALESCE(deleted_at, ?) WHEN ? != 'deleted' THEN NULL ELSE deleted_at END,
                    deleted_by = CASE WHEN ? = 'deleted' THEN ? WHEN ? != 'deleted' THEN NULL ELSE deleted_by END
                WHERE id = ?
                """,
                (
                    payload.get("code", before["code"]).strip().upper(),
                    payload.get("name", before["name"]).strip(),
                    payload.get("description", before.get("description", "")).strip(),
                    payload.get("category", before.get("category", "general")),
                    status,
                    int(bool(payload.get("allow_store_assignment", before["allow_store_assignment"]))),
                    int(bool(payload.get("allow_ai_agent_execution", before["allow_ai_agent_execution"]))),
                    int(bool(payload.get("allow_human_assignment", before["allow_human_assignment"]))),
                    int(bool(payload.get("requires_ceo_visibility_only", before["requires_ceo_visibility_only"] or status == "hidden"))),
                    payload.get("execution_mode", before.get("execution_mode", "suggest_only")),
                    payload.get("parent_department_id", before.get("parent_department_id")),
                    self._now(),
                    actor_id,
                    status,
                    deleted_at,
                    status,
                    status,
                    actor_id,
                    status,
                    department_id,
                ),
            )
            conn.commit()
            after = self.get_department(department_id)
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="department.update",
                resource_type="department",
                resource_id=department_id,
                before=before,
                after=after,
                department_id=department_id,
            )
            conn.commit()
            return after
        finally:
            conn.close()

    def set_department_status(self, department_id: str, status: str, *, actor_id: str = "ceo", actor_type: str = "human") -> Optional[dict]:
        current = self.get_department(department_id)
        if not current:
            return None
        return self.update_department(
            department_id,
            {
                "code": current["code"],
                "name": current["name"],
                "description": current.get("description", ""),
                "category": current.get("category", "general"),
                "status": status,
                "allow_store_assignment": current["allow_store_assignment"],
                "allow_ai_agent_execution": current["allow_ai_agent_execution"],
                "allow_human_assignment": current["allow_human_assignment"],
                "requires_ceo_visibility_only": current["requires_ceo_visibility_only"] or status == "hidden",
                "execution_mode": current.get("execution_mode", "suggest_only"),
                "parent_department_id": current.get("parent_department_id"),
            },
            actor_id=actor_id,
            actor_type=actor_type,
        )

    def list_department_permissions(self, department_id: str) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                """
                SELECT p.*, COALESCE(dp.allowed, 0) AS allowed
                FROM cp_permissions p
                LEFT JOIN cp_department_permissions dp
                    ON dp.permission_id = p.id AND dp.department_id = ?
                ORDER BY p.module ASC, p.permission_key ASC
                """,
                (department_id,),
            ).fetchall()
            results = []
            for row in rows:
                item = dict(row)
                item["allowed"] = self._bool(item.get("allowed"))
                results.append(item)
            return results
        finally:
            conn.close()

    def set_department_permissions(self, department_id: str, permissions: list[dict], *, actor_id: str = "ceo", actor_type: str = "human") -> List[dict]:
        now = self._now()
        conn = self._conn()
        try:
            before = self.list_department_permissions(department_id)
            permission_map = {
                row["permission_key"]: row["id"]
                for row in conn.execute("SELECT id, permission_key FROM cp_permissions").fetchall()
            }
            for item in permissions:
                permission_id = permission_map.get(item["key"])
                if not permission_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO cp_department_permissions (id, department_id, permission_id, allowed, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(department_id, permission_id) DO UPDATE SET
                        allowed = excluded.allowed,
                        updated_at = excluded.updated_at
                    """,
                    (str(uuid4()), department_id, permission_id, int(bool(item.get("allowed"))), now, now),
                )
            conn.commit()
            after = self.list_department_permissions(department_id)
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="department.permissions.update",
                resource_type="department_permission",
                resource_id=department_id,
                before={"permissions": before},
                after={"permissions": after},
                department_id=department_id,
            )
            conn.commit()
            return after
        finally:
            conn.close()

    def list_store_departments(self, store_id: str, *, actor_role: str = "ceo") -> List[dict]:
        departments = self.list_departments(actor_role=actor_role)
        conn = self._conn()
        try:
            rows = []
            for department in departments:
                assignment = self._store_department_assignment(conn, store_id, department["id"])
                rows.append(
                    {
                        "store_id": store_id,
                        "department_id": department["id"],
                        "department_code": department["code"],
                        "department_name": department["name"],
                        "status": department["status"],
                        "enabled": assignment["enabled"] if assignment else False,
                        "locked": assignment["locked"] if assignment else department["status"] == "locked",
                        "hidden": assignment["hidden"] if assignment else department["status"] == "hidden",
                        "deleted": assignment["deleted"] if assignment else department["status"] == "deleted",
                        "custom_policy_enabled": assignment["custom_policy_enabled"] if assignment else False,
                        "execution_mode": assignment["execution_mode"] if assignment and assignment.get("execution_mode") else department.get("execution_mode", "suggest_only"),
                        "custom_permissions_count": len(self._store_permission_overrides(conn, assignment["id"])) if assignment else 0,
                    }
                )
            return rows
        finally:
            conn.close()

    def upsert_store_departments(self, store_id: str, departments: list[dict], *, actor_id: str = "ceo", actor_type: str = "human") -> List[dict]:
        conn = self._conn()
        try:
            dept_lookup = {
                row["id"]: self._hydrate_department(row)
                for row in conn.execute("SELECT * FROM cp_departments").fetchall()
            }
            for item in departments:
                department = dept_lookup.get(item["department_id"])
                if not department or department["status"] == "deleted":
                    continue
                if department["status"] == "locked" and item.get("enabled", True):
                    item["locked"] = True
                now = self._now()
                conn.execute(
                    """
                    INSERT INTO cp_store_departments (
                        id, store_id, department_id, enabled, locked, hidden, deleted,
                        custom_policy_enabled, execution_mode, created_at, updated_at, created_by, updated_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(store_id, department_id) DO UPDATE SET
                        enabled = excluded.enabled,
                        locked = excluded.locked,
                        hidden = excluded.hidden,
                        deleted = excluded.deleted,
                        custom_policy_enabled = excluded.custom_policy_enabled,
                        execution_mode = excluded.execution_mode,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """,
                    (
                        str(uuid4()),
                        store_id,
                        department["id"],
                        int(bool(item.get("enabled"))),
                        int(bool(item.get("locked", False))),
                        int(bool(item.get("hidden", False))),
                        int(bool(item.get("deleted", False))),
                        int(bool(item.get("custom_policy_enabled", False))),
                        item.get("execution_mode"),
                        now,
                        now,
                        actor_id,
                        actor_id,
                    ),
                )
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="store.departments.update",
                resource_type="store_department",
                resource_id=store_id,
                after={"departments": departments},
                store_id=store_id,
            )
            conn.commit()
            return self.list_store_departments(store_id)
        finally:
            conn.close()

    def set_store_department_permissions(
        self,
        store_id: str,
        department_id: str,
        permissions: list[dict],
        *,
        actor_id: str = "ceo",
        actor_type: str = "human",
    ) -> dict:
        now = self._now()
        conn = self._conn()
        try:
            assignment = self._store_department_assignment(conn, store_id, department_id)
            if not assignment:
                raise ValueError("Store department assignment not found.")
            permission_map = {
                row["permission_key"]: row["id"]
                for row in conn.execute("SELECT id, permission_key FROM cp_permissions").fetchall()
            }
            before = self._store_permission_overrides(conn, assignment["id"])
            for item in permissions:
                permission_id = permission_map.get(item["key"])
                if not permission_id:
                    continue
                conn.execute(
                    """
                    INSERT INTO cp_store_department_permissions (
                        id, store_department_id, permission_id, allowed, source, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(store_department_id, permission_id) DO UPDATE SET
                        allowed = excluded.allowed,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(uuid4()),
                        assignment["id"],
                        permission_id,
                        int(bool(item.get("allowed"))),
                        item.get("source", "override"),
                        now,
                        now,
                    ),
                )
            after = self._store_permission_overrides(conn, assignment["id"])
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="store.department.permissions.update",
                resource_type="store_department_permission",
                resource_id=assignment["id"],
                before=before,
                after=after,
                store_id=store_id,
                department_id=department_id,
            )
            conn.commit()
            return {"store_id": store_id, "department_id": department_id, "permissions": after}
        finally:
            conn.close()

    def get_store_department_permissions(self, store_id: str, department_id: str) -> dict:
        conn = self._conn()
        try:
            assignment = self._store_department_assignment(conn, store_id, department_id)
            if not assignment:
                raise ValueError("Store department assignment not found.")
            overrides = self._store_permission_overrides(conn, assignment["id"])
            rows = conn.execute(
                """
                SELECT p.*, COALESCE(dp.allowed, 0) AS default_allowed
                FROM cp_permissions p
                LEFT JOIN cp_department_permissions dp
                    ON dp.permission_id = p.id AND dp.department_id = ?
                ORDER BY p.module ASC, p.permission_key ASC
                """,
                (department_id,),
            ).fetchall()
            permissions = []
            for row in rows:
                item = dict(row)
                default_allowed = self._bool(item.get("default_allowed"))
                override_value = overrides.get(item["permission_key"])
                permissions.append(
                    {
                        "permission_key": item["permission_key"],
                        "permission_name": item["permission_name"],
                        "module": item["module"],
                        "action": item["action"],
                        "default_allowed": default_allowed,
                        "allowed": override_value if override_value is not None else default_allowed,
                        "source": "override" if override_value is not None else "default",
                    }
                )
            return {
                "store_id": store_id,
                "department_id": department_id,
                "store_department_id": assignment["id"],
                "permissions": permissions,
            }
        finally:
            conn.close()

    def list_policies(
        self,
        *,
        scope_type: str | None = None,
        target_type: str | None = None,
        is_active: bool | None = None,
    ) -> List[dict]:
        conditions = []
        params: list[Any] = []
        if scope_type:
            conditions.append("scope_type = ?")
            params.append(scope_type)
        if target_type:
            conditions.append("target_type = ?")
            params.append(target_type)
        if is_active is not None:
            conditions.append("is_active = ?")
            params.append(int(bool(is_active)))
        sql = "SELECT * FROM cp_policies"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY priority ASC, created_at DESC"
        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [item for item in (self._hydrate_policy(row) for row in rows) if item]
        finally:
            conn.close()

    def get_policy(self, policy_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cp_policies WHERE id = ?", (policy_id,)).fetchone()
            return self._hydrate_policy(row)
        finally:
            conn.close()

    def _create_policy_version(
        self,
        conn: sqlite3.Connection,
        *,
        policy_id: str,
        snapshot: dict,
        created_by: str = "",
        change_note: str = "",
    ) -> None:
        version_row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) AS v FROM cp_policy_versions WHERE policy_id = ?",
            (policy_id,),
        ).fetchone()
        next_version = (version_row["v"] if version_row else 0) + 1
        conn.execute(
            """
            INSERT INTO cp_policy_versions (
                id, policy_id, version_number, snapshot_json, change_note, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                policy_id,
                next_version,
                json.dumps(snapshot or {}, ensure_ascii=False),
                change_note,
                created_by,
                self._now(),
            ),
        )

    def list_policy_versions(self, policy_id: str) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM cp_policy_versions WHERE policy_id = ? ORDER BY version_number DESC",
                (policy_id,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["snapshot"] = self._decode_json(item.get("snapshot_json"))
                result.append(item)
            return result
        finally:
            conn.close()

    def rollback_policy_version(self, policy_id: str, version_id: str, *, actor_id: str = "ceo", actor_type: str = "human") -> Optional[dict]:
        conn = self._conn()
        try:
            version = conn.execute(
                "SELECT * FROM cp_policy_versions WHERE id = ? AND policy_id = ?",
                (version_id, policy_id),
            ).fetchone()
            current = self.get_policy(policy_id)
            if not version or not current:
                return None
            snapshot = self._decode_json(version["snapshot_json"])
            conn.execute(
                """
                UPDATE cp_policies
                SET policy_code = ?, policy_name = ?, scope_type = ?, target_type = ?, target_id = ?,
                    condition_json = ?, effect = ?, approval_chain_json = ?, escalation_json = ?,
                    audit_required = ?, priority = ?, is_active = ?, effective_from = ?, effective_to = ?,
                    updated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    snapshot.get("policy_code", current["policy_code"]),
                    snapshot.get("policy_name", current["policy_name"]),
                    snapshot.get("scope_type", current["scope_type"]),
                    snapshot.get("target_type", current["target_type"]),
                    str(snapshot.get("target_id", current["target_id"])),
                    json.dumps(snapshot.get("condition") or {}, ensure_ascii=False),
                    snapshot.get("effect", current["effect"]),
                    json.dumps(snapshot.get("approval_chain") or [], ensure_ascii=False),
                    json.dumps(snapshot.get("escalation") or {}, ensure_ascii=False),
                    int(bool(snapshot.get("audit_required", current["audit_required"]))),
                    int(snapshot.get("priority", current["priority"])),
                    int(bool(snapshot.get("is_active", current["is_active"]))),
                    snapshot.get("effective_from", current.get("effective_from")),
                    snapshot.get("effective_to", current.get("effective_to")),
                    actor_id,
                    self._now(),
                    policy_id,
                ),
            )
            rolled = self.get_policy(policy_id)
            self._create_policy_version(
                conn,
                policy_id=policy_id,
                snapshot=rolled or {},
                created_by=actor_id,
                change_note=f"Rollback to version {version['version_number']}",
            )
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="policy.rollback",
                resource_type="policy",
                resource_id=policy_id,
                before=current,
                after=rolled,
                reason=f"Rollback to version {version['version_number']}",
            )
            conn.commit()
            return self.get_policy(policy_id)
        finally:
            conn.close()

    def create_policy(self, payload: dict, *, actor_id: str = "ceo", actor_type: str = "human") -> dict:
        now = self._now()
        policy_id = str(uuid4())
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO cp_policies (
                    id, policy_code, policy_name, scope_type, target_type, target_id,
                    condition_json, effect, approval_chain_json, escalation_json,
                    audit_required, priority, is_active, effective_from, effective_to,
                    created_by, updated_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    policy_id,
                    payload["policy_code"].strip().upper(),
                    payload["policy_name"].strip(),
                    payload["scope_type"],
                    payload["target_type"],
                    str(payload["target_id"]),
                    json.dumps(payload.get("condition_json") or {}, ensure_ascii=False),
                    payload["effect"],
                    json.dumps(payload.get("approval_chain_json") or [], ensure_ascii=False),
                    json.dumps(payload.get("escalation_json") or {}, ensure_ascii=False),
                    int(bool(payload.get("audit_required", True))),
                    int(payload.get("priority", 100)),
                    int(bool(payload.get("is_active", True))),
                    payload.get("effective_from"),
                    payload.get("effective_to"),
                    actor_id,
                    actor_id,
                    now,
                    now,
                ),
            )
            snapshot = self._hydrate_policy(conn.execute("SELECT * FROM cp_policies WHERE id = ?", (policy_id,)).fetchone())
            self._create_policy_version(
                conn,
                policy_id=policy_id,
                snapshot=snapshot or {},
                created_by=actor_id,
                change_note="Policy created",
            )
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="policy.create",
                resource_type="policy",
                resource_id=policy_id,
                after={"policy_code": payload["policy_code"].strip().upper(), "effect": payload["effect"]},
            )
            conn.commit()
            return self.get_policy(policy_id) or {"id": policy_id}
        finally:
            conn.close()

    def update_policy(self, policy_id: str, payload: dict, *, actor_id: str = "ceo", actor_type: str = "human") -> Optional[dict]:
        conn = self._conn()
        try:
            before = self.get_policy(policy_id)
            if not before:
                return None
            conn.execute(
                """
                UPDATE cp_policies
                SET policy_code = ?, policy_name = ?, scope_type = ?, target_type = ?, target_id = ?,
                    condition_json = ?, effect = ?, approval_chain_json = ?, escalation_json = ?,
                    audit_required = ?, priority = ?, is_active = ?, effective_from = ?, effective_to = ?,
                    updated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    payload.get("policy_code", before["policy_code"]).strip().upper(),
                    payload.get("policy_name", before["policy_name"]).strip(),
                    payload.get("scope_type", before["scope_type"]),
                    payload.get("target_type", before["target_type"]),
                    str(payload.get("target_id", before["target_id"])),
                    json.dumps(payload.get("condition_json", before.get("condition")) or {}, ensure_ascii=False),
                    payload.get("effect", before["effect"]),
                    json.dumps(payload.get("approval_chain_json", before.get("approval_chain")) or [], ensure_ascii=False),
                    json.dumps(payload.get("escalation_json", before.get("escalation")) or {}, ensure_ascii=False),
                    int(bool(payload.get("audit_required", before["audit_required"]))),
                    int(payload.get("priority", before["priority"])),
                    int(bool(payload.get("is_active", before["is_active"]))),
                    payload.get("effective_from", before.get("effective_from")),
                    payload.get("effective_to", before.get("effective_to")),
                    actor_id,
                    self._now(),
                    policy_id,
                ),
            )
            conn.commit()
            after = self.get_policy(policy_id)
            self._create_policy_version(
                conn,
                policy_id=policy_id,
                snapshot=after or {},
                created_by=actor_id,
                change_note=payload.get("change_note", "Policy updated") if isinstance(payload, dict) else "Policy updated",
            )
            self._log_audit(
                conn,
                actor_type=actor_type,
                actor_id=actor_id,
                action="policy.update",
                resource_type="policy",
                resource_id=policy_id,
                before=before,
                after=after,
            )
            conn.commit()
            return after
        finally:
            conn.close()

    def set_policy_active(self, policy_id: str, is_active: bool, *, actor_id: str = "ceo", actor_type: str = "human") -> Optional[dict]:
        return self.update_policy(policy_id, {"is_active": is_active}, actor_id=actor_id, actor_type=actor_type)

    def list_audit_logs(
        self,
        *,
        store_id: str | None = None,
        department_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
    ) -> List[dict]:
        conditions = []
        params: list[Any] = []
        if store_id:
            conditions.append("store_id = ?")
            params.append(store_id)
        if department_id:
            conditions.append("department_id = ?")
            params.append(department_id)
        if resource_type:
            conditions.append("resource_type = ?")
            params.append(resource_type)
        sql = "SELECT * FROM cp_audit_logs"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        conn = self._conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [item for item in (self._hydrate_audit_log(row) for row in rows) if item]
        finally:
            conn.close()

    def list_policy_simulations(self, *, limit: int = 50, policy_id: str | None = None) -> List[dict]:
        conn = self._conn()
        try:
            if policy_id:
                rows = conn.execute(
                    "SELECT * FROM cp_policy_simulations WHERE policy_id = ? ORDER BY created_at DESC LIMIT ?",
                    (policy_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_policy_simulations ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item["context"] = self._decode_json(item.get("context_json"))
                item["result"] = self._decode_json(item.get("result_json"))
                items.append(item)
            return items
        finally:
            conn.close()

    def evaluate_governance_action(self, payload: dict) -> dict:
        actor_role = (payload.get("actor_role") or "").lower()
        store_id = payload.get("store_id")
        department_id = payload.get("department_id")
        permission_key = payload.get("permission_key")
        action_name = payload.get("action")
        context = payload.get("context") or {}
        conn = self._conn()
        try:
            department = self.get_department(department_id, actor_role=actor_role or "ceo")
            if not department:
                return {"allowed": False, "decision": "deny", "reason": "department_not_found", "matched_policy": None, "escalation": None}
            if department["status"] == "deleted":
                return {"allowed": False, "decision": "deny", "reason": "department_deleted", "matched_policy": None, "escalation": None}
            if department["status"] == "hidden" and actor_role not in {"ceo", "super_admin"}:
                return {"allowed": False, "decision": "deny", "reason": "department_hidden", "matched_policy": "POLICY_003_HIDDEN_DEPARTMENT_VISIBILITY", "escalation": "ceo"}
            if department["status"] == "locked":
                return {"allowed": False, "decision": "deny", "reason": "department_locked", "matched_policy": "POLICY_004_LOCKED_DEPARTMENT_EXECUTION", "escalation": None}

            assignment = self._store_department_assignment(conn, store_id, department_id) if store_id else None
            if store_id and (not assignment or not assignment.get("enabled") or assignment.get("deleted")):
                return {"allowed": False, "decision": "deny", "reason": "store_department_not_enabled", "matched_policy": None, "escalation": None}
            if assignment and assignment.get("locked"):
                return {"allowed": False, "decision": "deny", "reason": "store_department_locked", "matched_policy": None, "escalation": None}
            if assignment and assignment.get("hidden") and actor_role not in {"ceo", "super_admin"}:
                return {"allowed": False, "decision": "deny", "reason": "store_department_hidden", "matched_policy": None, "escalation": "ceo"}
            if permission_key and not self._effective_permission(conn, department_id, permission_key, store_id):
                return {"allowed": False, "decision": "deny", "reason": "permission_denied", "matched_policy": None, "escalation": None}

            evaluation_context = {
                **context,
                "action": action_name,
                "store_id": store_id,
                "department_id": department_id,
                "department_code": department["code"],
                "department_status": department["status"],
                "actor_role": actor_role,
            }
            policies = self.list_policies(is_active=True)
            priority_rank = {"action": 0, "role": 1, "department": 2, "store": 3, "company": 4}
            candidates = sorted(
                policies,
                key=lambda item: (priority_rank.get(item["scope_type"], 99), int(item.get("priority", 100))),
            )
            matched = None
            for policy in candidates:
                scope = policy["scope_type"]
                target_ok = (
                    scope == "company"
                    or (scope == "store" and str(policy["target_id"]) == str(store_id))
                    or (scope == "department" and str(policy["target_id"]) in {str(department_id), department["code"]})
                    or (scope == "role" and str(policy["target_id"]).lower() == actor_role)
                    or (scope == "action" and str(policy["target_id"]) == action_name)
                )
                if not target_ok or not self._match_condition(evaluation_context, policy.get("condition")):
                    continue
                matched = policy
                break

            decision = "allow"
            allowed = True
            escalation = None
            approval_chain = []
            if matched:
                effect = matched["effect"]
                approval_chain = matched.get("approval_chain") or []
                escalation = (matched.get("escalation") or {}).get("target")
                if effect == "deny":
                    allowed = False
                    decision = "deny"
                elif effect in {"require_approval", "require_ceo_approval"}:
                    allowed = False
                    decision = effect
                elif effect == "suggest_only":
                    decision = "suggest_only"
                elif effect == "auto_execute":
                    decision = "auto_execute"
                elif effect == "escalate":
                    allowed = False
                    decision = "escalate"
                elif effect == "ceo_only_visibility":
                    allowed = actor_role in {"ceo", "super_admin"}
                    decision = "allow" if allowed else "deny"

            simulation_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO cp_policy_simulations (
                    id, policy_id, actor_type, actor_id, actor_role, store_id, department_id,
                    action, permission_key, context_json, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    matched["id"] if matched else None,
                    payload.get("actor_type", "human"),
                    payload.get("actor_id", "unknown"),
                    actor_role,
                    store_id,
                    department_id,
                    action_name,
                    permission_key,
                    json.dumps(context, ensure_ascii=False),
                    json.dumps(
                        {
                            "allowed": allowed,
                            "decision": decision,
                            "matched_policy": matched["policy_code"] if matched else None,
                            "escalation": escalation,
                            "approval_chain": approval_chain,
                        },
                        ensure_ascii=False,
                    ),
                    self._now(),
                ),
            )

            if (matched and matched.get("audit_required")) or decision != "allow":
                self._log_audit(
                    conn,
                    actor_type=payload.get("actor_type", "human"),
                    actor_id=payload.get("actor_id", "unknown"),
                    action=f"governance.evaluate.{decision}",
                    resource_type="department_action",
                    resource_id=f"{department_id}:{action_name}",
                    after={"decision": decision, "matched_policy": matched["policy_code"] if matched else None},
                    status="success" if allowed else "blocked",
                    reason=decision,
                    store_id=store_id,
                    department_id=department_id,
                )
            conn.commit()

            return {
                "allowed": allowed,
                "decision": decision,
                "matched_policy": matched["policy_code"] if matched else None,
                "escalation": escalation,
                "approval_chain": approval_chain,
                "execution_mode": assignment.get("execution_mode") if assignment and assignment.get("execution_mode") else department.get("execution_mode", "suggest_only"),
                "simulation_id": simulation_id,
            }
        finally:
            conn.close()

    def request_governed_action(self, payload: dict) -> dict:
        result = self.evaluate_governance_action(payload)
        if result["decision"] not in {"require_approval", "require_ceo_approval"}:
            return {"status": result["decision"], "evaluation": result, "approval": None}

        approval_level = "ceo" if result["decision"] == "require_ceo_approval" else ((result.get("approval_chain") or ["supervisor"])[0])
        approval = self.request_approval(
            payload.get("task_id") or f"governance:{payload.get('department_id')}:{payload.get('action')}",
            requested_by=payload.get("actor_id", "agentai"),
            resource_type="department_action",
            resource_id=f"{payload.get('department_id')}:{payload.get('action')}",
            approval_level=approval_level,
            policy_code=result.get("matched_policy") or "",
            store_id=payload.get("store_id"),
            department_id=payload.get("department_id"),
            request_payload={
                "actor_type": payload.get("actor_type", "agent"),
                "actor_id": payload.get("actor_id", "agentai"),
                "actor_role": payload.get("actor_role", ""),
                "action": payload.get("action"),
                "permission_key": payload.get("permission_key"),
                "context": payload.get("context") or {},
                "evaluation": result,
            },
        )
        return {"status": "pending_approval", "evaluation": result, "approval": approval}

    def execute_governance_approval(self, approval_id: str, *, actor_id: str = "system") -> dict | None:
        conn = self._conn()
        try:
            approval_row = conn.execute("SELECT * FROM cp_approvals WHERE id = ?", (approval_id,)).fetchone()
            approval = self._hydrate_approval(approval_row)
            if not approval or approval.get("status") != "approved" or approval.get("resource_type") != "department_action":
                return None
            decision = approval.get("decision") or {}
            if decision.get("executed"):
                return decision

            request_payload = approval.get("request") or {}
            action_name = request_payload.get("action", approval.get("resource_id", "department_action"))
            department_id = approval.get("department_id")
            store_id = approval.get("store_id")
            execution = {
                "executed": True,
                "executed_at": self._now(),
                "task": None,
                "edge_command": None,
            }

            title = f"Governed action approved: {action_name}"
            description = f"Approved governance action for department {department_id or 'unknown'} at store {store_id or 'n/a'}."
            task = self.create_task(
                title=title,
                assigned_agent_id="workflow",
                goal_id="",
                description=description,
                task_type="governed_action",
                priority=2,
                context_json={
                    "approval_id": approval_id,
                    "resource_type": approval.get("resource_type"),
                    "resource_id": approval.get("resource_id"),
                    "request": request_payload,
                },
            )
            execution["task"] = task

            edge_spec = request_payload.get("edge_command") or {}
            if edge_spec.get("project_id") and edge_spec.get("machine_id") and edge_spec.get("command_type"):
                edge_command = self.create_edge_command(
                    project_id=edge_spec["project_id"],
                    machine_id=edge_spec["machine_id"],
                    machine_name=edge_spec.get("machine_name", edge_spec["machine_id"]),
                    command_type=edge_spec["command_type"],
                    payload=edge_spec.get("payload"),
                    title=edge_spec.get("title", title),
                    created_by=actor_id,
                    source_suggestion_id="governance-approval",
                )
                execution["edge_command"] = edge_command

            conn.execute(
                "UPDATE cp_approvals SET decision_json = ? WHERE id = ?",
                (json.dumps({**decision, **execution}, ensure_ascii=False), approval_id),
            )
            self._log_audit(
                conn,
                actor_type="system",
                actor_id=actor_id,
                action="governance.approval.execute",
                resource_type="approval",
                resource_id=approval_id,
                after=execution,
                status="success",
                store_id=store_id,
                department_id=department_id,
            )
            conn.commit()
            return execution
        finally:
            conn.close()

    # ── metrics / stats ───────────────────────────────────────────────

    def get_dashboard_stats(self) -> dict:
        conn = self._conn()
        try:
            task_counts = {}
            for status in ("pending", "running", "success", "failed"):
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM cp_tasks WHERE status = ?", (status,)
                ).fetchone()
                task_counts[status] = row["c"] if row else 0

            agent_count = conn.execute("SELECT COUNT(*) as c FROM cp_agents").fetchone()
            job_count = conn.execute("SELECT COUNT(*) as c FROM cp_jobs").fetchone()
            goal_count = conn.execute("SELECT COUNT(*) as c FROM goals").fetchone()

            total_cost = conn.execute(
                "SELECT COALESCE(SUM(cost), 0) as total FROM cp_jobs"
            ).fetchone()

            return {
                "tasks": task_counts,
                "agents": agent_count["c"] if agent_count else 0,
                "jobs": job_count["c"] if job_count else 0,
                "goals": goal_count["c"] if goal_count else 0,
                "total_cost_usd": round(total_cost["total"], 2) if total_cost else 0,
            }
        finally:
            conn.close()
