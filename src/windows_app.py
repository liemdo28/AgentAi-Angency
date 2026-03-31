"""Desktop dashboard for AgentAI Agency — Owner/Admin Console.

Run:
    python src/windows_app.py

Requires:
    pip install -r requirements.txt
"""
from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, timezone
from tkinter import messagebox, ttk
from tkinter import font as tkfont
from tkinter import filedialog
from typing import Any
import json
import logging

import sys
from pathlib import Path

# Stub heavy deps so imports fail gracefully on missing packages
_HEAVY = [
    "langgraph", "langgraph.graph", "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "anthropic", "openai", "httpx", "sendgrid", "dotenv",
]
for _m in _HEAVY:
    sys.modules.setdefault(_m, type(sys)(_m))

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data Layer — read directly from SQLite + JSON store
# ──────────────────────────────────────────────────────────────────────────────

def _init_db() -> None:
    """Ensure DB tables exist (idempotent)."""
    from src.db.connection import get_db
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, campaign_id TEXT, account_id TEXT,
            goal TEXT NOT NULL, description TEXT, task_type TEXT,
            status TEXT DEFAULT 'draft', priority INTEGER DEFAULT 2,
            kpis TEXT, kpi_results TEXT, score REAL DEFAULT 0,
            created_at TEXT, deadline TEXT, sla_deadline TEXT,
            started_at TEXT, completed_at TEXT, current_department TEXT,
            assigned_employees TEXT, dependencies TEXT, dependents TEXT,
            step_index INTEGER DEFAULT 0, planning_mode TEXT DEFAULT 'template',
            health_flags TEXT, retry_count INTEGER DEFAULT 0,
            escalation_count INTEGER DEFAULT 0, final_output_text TEXT,
            final_output_json TEXT, specialist_outputs_json TEXT, notes TEXT
        )""")
    db.execute("""
        CREATE TABLE IF NOT EXISTS review_history (
            id TEXT PRIMARY KEY, task_id TEXT, step_name TEXT,
            score REAL, threshold REAL, decision TEXT, feedback TEXT,
            breakdown_json TEXT, mode TEXT, model_version TEXT,
            created_at TEXT DEFAULT (datetime('now')))""")
    db.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY, actor TEXT, action_type TEXT,
            entity_type TEXT, entity_id TEXT, details_json TEXT,
            timestamp TEXT DEFAULT (datetime('now')))""")
    db.commit()


def _load_tasks(status: str | None = None, department: str | None = None,
                search: str | None = None) -> list[dict]:
    """Load tasks from SQLite."""
    from src.db.connection import get_db
    db = get_db()
    conditions, params = [], []
    if status:
        conditions.append("status = ?"); params.append(status)
    if department:
        conditions.append("current_department = ?"); params.append(department)
    if search:
        conditions.append("(goal LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = db.execute(
        f"SELECT * FROM tasks WHERE {where} ORDER BY created_at DESC LIMIT 500",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def _load_stats() -> dict[str, Any]:
    """Load dashboard stats from SQLite."""
    from src.db.connection import get_db
    db = get_db()
    def n(where: str) -> int:
        r = db.execute(f"SELECT COUNT(*) as c FROM tasks WHERE {where}").fetchone()
        return dict(r)["c"]

    total = n("1=1")
    passed = n("status IN ('passed','done')")
    failed = n("status IN ('failed','cancelled')")
    active = n("status NOT IN ('passed','done','failed','cancelled')")
    review = n("status = 'review'")
    escalated = n("status = 'escalated'")

    r = db.execute(
        "SELECT AVG(score) as a FROM tasks WHERE score IS NOT NULL AND score > 0"
    ).fetchone()
    avg_score = round(dict(r)["a"] or 0.0, 1)
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0.0

    return dict(total=total, active=active, passed=passed, failed=failed,
                review=review, escalated=escalated, avg_score=avg_score,
                pass_rate=pass_rate)


def _load_handoffs() -> dict[str, int]:
    """Load handoff counts from JSON store."""
    from src.config.settings import SETTINGS
    from src.store import load
    try:
        store_file = Path(__file__).parent.parent / "agency_state.json"
        if store_file.exists():
            state = load()
        else:
            state = {}
    except Exception:
        state = {}
    counts = {"draft": 0, "approved": 0, "blocked": 0, "overdue": 0}
    for h in state.values():
        s = h.get("state", "draft")
        if s in counts:
            counts[s] += 1
    return counts


def _create_task(goal: str, description: str, task_type: str,
                 department: str, priority: int,
                 kpis: dict[str, float] | None,
                 account_id: str = "") -> str:
    """Create a task in the DB. Returns task_id."""
    import uuid
    from src.db.connection import get_db
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = get_db()
    db.execute("""
        INSERT INTO tasks (id, goal, description, task_type, current_department,
                           priority, kpis, status, created_at, account_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
               (task_id, goal, description, task_type, department,
                priority, json.dumps(kpis or {}), now, account_id))
    db.commit()
    return task_id


def _run_task(task_id: str, background: bool = True) -> dict:
    """Run a task through the LangGraph pipeline."""
    try:
        from src.db.connection import init_db
        init_db()
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import TaskStatus
        from src.task_runner import run_task_sync
        repo = TaskRepository()
        task = repo.get(task_id)
        if not task:
            return {"ok": False, "error": "Task not found"}

        if background:
            t = threading.Thread(target=run_task_sync, args=(task, None), daemon=True)
            t.start()
            return {"ok": True, "message": "Task started in background"}
        else:
            return run_task_sync(task, None)
    except Exception as exc:
        logger.exception("run_task failed")
        return {"ok": False, "error": str(exc)}


def _cancel_task(task_id: str) -> dict:
    """Cancel a task."""
    try:
        from src.db.connection import get_db
        db = get_db()
        db.execute(
            "UPDATE tasks SET status = 'cancelled' WHERE id = ? AND status NOT IN ('passed','done','failed','cancelled')",
            (task_id,))
        db.commit()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _load_review_history(task_id: str) -> list[dict]:
    """Load review history for a task."""
    from src.db.connection import get_db
    db = get_db()
    rows = db.execute(
        "SELECT * FROM review_history WHERE task_id = ? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _export_csv(filepath: str) -> int:
    """Export all tasks to CSV. Returns row count."""
    from src.db.connection import get_db
    db = get_db()
    rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    if not rows:
        return 0
    import csv
    headers = list(dict(rows[0]).keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    return len(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

DEPARTMENTS = [
    "strategy", "creative", "media", "data", "account",
    "tech", "sales", "operations", "finance", "crm_automation", "production",
]
TASK_TYPES = [
    "campaign_launch", "campaign_optimization", "retention_program",
    "client_reporting", "ad_hoc",
]
STATUS_COLORS = {
    "draft": "#94a3b8", "pending": "#60a5fa", "in_progress": "#2d6cea",
    "review": "#f59e0b", "passed": "#1ea672", "done": "#1ea672",
    "failed": "#ef4444", "cancelled": "#94a3b8", "escalated": "#f97316",
    "blocked": "#ef4444",
}
PRIORITY_LABELS = {1: "Low", 2: "Normal", 3: "High", 4: "Urgent"}


# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

class AgencyDesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AgentAI Agency — Admin Console")
        self.geometry("1440x900")
        self.minsize(1200, 700)
        self._selected_task_id: str | None = None
        self._auto_refresh_id: str | None = None

        self.base_font = tkfont.nametofont("TkDefaultFont")
        self.base_font.configure(family="Segoe UI", size=10)

        self._init_db()
        self._build_style()
        self._build_layout()
        self._bind_events()
        self.refresh()

    def _init_db(self) -> None:
        try:
            _init_db()
        except Exception as exc:
            messagebox.showwarning("DB Init", f"Could not init DB: {exc}")

    # ── Style ──────────────────────────────────────────────────────────────────

    def _build_style(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")

        self.C = {
            "bg": "#0f1117", "panel": "#1a1d27", "panel2": "#21253a",
            "text": "#e8eaf0", "muted": "#8892a4", "border": "#2d3454",
            "primary": "#4f8ef7", "primary_hover": "#3b74d8",
            "success": "#22c55e", "warning": "#f59e0b", "danger": "#ef4444",
            "accent": "#8b5cf6",
        }
        self.configure(bg=self.C["bg"])

        s.configure("App.TFrame", background=self.C["bg"])
        s.configure("Panel.TFrame", background=self.C["panel"], relief="flat")
        s.configure("Panel2.TFrame", background=self.C["panel2"], relief="flat")

        s.configure("Title.TLabel",
                    background=self.C["bg"], foreground=self.C["text"],
                    font=("Segoe UI Semibold", 20))
        s.configure("Subtitle.TLabel",
                    background=self.C["bg"], foreground=self.C["muted"],
                    font=("Segoe UI", 10))
        s.configure("H1.TLabel",
                    background=self.C["panel"], foreground=self.C["text"],
                    font=("Segoe UI Semibold", 13))
        s.configure("H2.TLabel",
                    background=self.C["panel"], foreground=self.C["text"],
                    font=("Segoe UI Semibold", 11))
        s.configure("Caption.TLabel",
                    background=self.C["panel"], foreground=self.C["muted"],
                    font=("Segoe UI", 9))
        s.configure("Metric.TLabel",
                    background=self.C["panel"], foreground=self.C["text"],
                    font=("Segoe UI Semibold", 26))
        s.configure("Status.TLabel",
                    font=("Segoe UI Semibold", 9))

        s.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        s.configure("Primary.TButton",
                    font=("Segoe UI Semibold", 10), padding=(12, 7))
        s.configure("Danger.TButton",
                    font=("Segoe UI Semibold", 9))

        # Treeview
        s.configure("Treeview",
                    font=("Segoe UI", 10),
                    rowheight=32,
                    fieldbackground=self.C["panel"],
                    foreground=self.C["text"],
                    bordercolor=self.C["border"])
        s.configure("Treeview.Heading",
                    font=("Segoe UI Semibold", 10),
                    background="#252a3d",
                    foreground=self.C["text"],
                    relief="flat")

    # ── Layout ─────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        root = ttk.Frame(self, style="App.TFrame")
        root.pack(fill="both", expand=True)

        # ── Header ──
        header = ttk.Frame(root, style="App.TFrame", padding=(20, 14, 20, 8))
        header.pack(fill="x")

        ttk.Label(header, text="AgentAI Agency", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Admin Console", style="Subtitle.TLabel").pack(
            side="left", padx=(12, 0), pady=(12, 0))

        btn_frame = ttk.Frame(header, style="App.TFrame")
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="⟳  Refresh", command=self.refresh).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="+  New Task", command=self._show_create_dialog,
                   style="Primary.TButton").pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Export CSV", command=self._export).pack(side="left")

        # ── Metrics bar ──
        metrics = ttk.Frame(root, style="App.TFrame", padding=(20, 0, 20, 8))
        metrics.pack(fill="x")
        self._metric_labels: dict[str, tuple[ttk.Label, ttk.Label]] = {}
        for key, label, color in [
            ("total", "Total Tasks", self.C["muted"]),
            ("active", "Active", self.C["primary"]),
            ("passed", "Passed", self.C["success"]),
            ("failed", "Failed", self.C["danger"]),
            ("review", "In Review", self.C["warning"]),
            ("escalated", "Escalated", "#f97316"),
            ("avg_score", "Avg Score", self.C["accent"]),
            ("pass_rate", "Pass Rate", self.C["success"]),
        ]:
            card = tk.Frame(metrics, bg=self.C["panel"], relief="flat", bd=0)
            card.pack(side="left", padx=(0, 8), pady=(0, 4))
            vl = tk.Label(card, text="—", bg=self.C["panel"],
                          fg=color, font=("Segoe UI Semibold", 22))
            vl.pack(padx=(14, 8), pady=(10, 0))
            tk.Label(card, text=label, bg=self.C["panel"],
                     fg=self.C["muted"], font=("Segoe UI", 9)).pack(
                         padx=(14, 8), pady=(0, 8))
            self._metric_labels[key] = vl

        # ── Main area ──
        main = ttk.Frame(root, style="App.TFrame", padding=(20, 0, 20, 16))
        main.pack(fill="both", expand=True)
        main.grid_columnconfigure(0, weight=5)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        # ── Left: Task list ──
        left = ttk.Frame(main, style="Panel.TFrame", padding=(14, 12))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        # Toolbar
        toolbar = ttk.Frame(left, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        toolbar.grid_columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Tasks", style="H1.TLabel").grid(row=0, column=0, sticky="w")

        filter_frame = ttk.Frame(toolbar, style="Panel.TFrame")
        filter_frame.grid(row=0, column=1, sticky="e")

        ttk.Label(filter_frame, text="Status:", style="Caption.TLabel").pack(side="left", padx=(0, 4))
        self._status_filter = ttk.Combobox(
            filter_frame, values=["All", "draft", "pending", "in_progress",
                                   "review", "passed", "done", "failed",
                                   "escalated", "cancelled"],
            state="readonly", width=14, font=("Segoe UI", 9))
        self._status_filter.current(0)
        self._status_filter.pack(side="left", padx=4)
        self._status_filter.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        ttk.Label(filter_frame, text="Dept:", style="Caption.TLabel").pack(side="left", padx=(8, 4))
        self._dept_filter = ttk.Combobox(
            filter_frame, values=["All"] + DEPARTMENTS,
            state="readonly", width=12, font=("Segoe UI", 9))
        self._dept_filter.current(0)
        self._dept_filter.pack(side="left", padx=4)
        self._dept_filter.bind("<<ComboboxSelected>>", lambda _: self.refresh())

        self._search_var = tk.StringVar()
        search = ttk.Entry(toolbar, textvariable=self._search_var, width=20)
        search.grid(row=0, column=2, sticky="e", padx=(8, 0))
        search.bind("<Return>", lambda _: self.refresh())
        ttk.Button(toolbar, text="Search", command=self.refresh).grid(
            row=0, column=3, sticky="e", padx=(4, 0))

        # Table
        cols = ("id", "goal", "dept", "type", "status", "priority", "score", "updated")
        self._tree = ttk.Treeview(left, columns=cols, show="headings",
                                   style="Treeview")
        self._tree.pack(fill="both", expand=True)

        col_cfg = {
            "id": ("Task ID", 130), "goal": ("Goal / Description", 360),
            "dept": ("Dept", 110), "type": ("Type", 140),
            "status": ("Status", 100), "priority": ("Pri", 45),
            "score": ("Score", 55), "updated": ("Updated", 130),
        }
        for col, (label, width) in col_cfg.items():
            self._tree.heading(col, text=label)
            anchor = "w" if col == "goal" else "center"
            stretch = (col == "goal")
            self._tree.column(col, width=width, anchor=anchor,
                              stretch=stretch, minwidth=60)

        scroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self._tree.pack(side="left", fill="both", expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_task_select)
        self._tree.bind("<Double-Button-1>", lambda _: self._show_task_detail())

        # Action bar
        actions = ttk.Frame(left, style="Panel.TFrame", padding=(0, 8, 0, 0))
        actions.pack(fill="x")
        self._btn_run = ttk.Button(actions, text="▶  Run Task",
                                    style="Primary.TButton", command=self._run_selected)
        self._btn_run.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Cancel Task", command=self._cancel_selected).pack(
            side="left", padx=(0, 8))
        ttk.Button(actions, text="View Detail", command=self._show_task_detail).pack(
            side="left")

        # ── Right: Detail + Handoffs ──
        right = ttk.Frame(main, style="App.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=0)
        right.grid_columnconfigure(0, weight=1)

        # Task detail
        self._detail = TaskDetailPanel(right, self)
        self._detail.frame.grid(row=0, column=0, sticky="nsew", pady=(0, 12))

        # Handoff status
        hframe = ttk.Frame(right, style="Panel.TFrame", padding=(14, 10))
        hframe.grid(row=1, column=0, sticky="nsew")
        hframe.grid_columnconfigure(0, weight=1)
        tk.Label(hframe, text="Handoffs", bg=self.C["panel"],
                 fg=self.C["text"], font=("Segoe UI Semibold", 12)).grid(
                     row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self._handoff_labels = {}
        for i, (state, color) in enumerate([
            ("draft", "#60a5fa"), ("approved", "#22c55e"),
            ("blocked", "#ef4444"), ("overdue", "#f97316"),
        ]):
            lbl = tk.Label(hframe, text="0", bg=self.C["panel2"],
                           fg=color, font=("Segoe UI Semibold", 16))
            lbl.grid(row=1, column=i, sticky="nsew", padx=3, pady=4)
            tk.Label(hframe, text=state.capitalize(), bg=self.C["panel"],
                     fg=self.C["muted"], font=("Segoe UI", 8)).grid(
                         row=2, column=i, padx=3, pady=(0, 4))
            self._handoff_labels[state] = lbl

    # ── Events ─────────────────────────────────────────────────────────────────

    def _bind_events(self) -> None:
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self._auto_refresh_id:
            self.after_cancel(self._auto_refresh_id)
        self.destroy()

    def _on_task_select(self, _=None) -> None:
        sel = self._tree.selection()
        self._selected_task_id = self._tree.item(sel[0])["values"][0] if sel else None

    # ── Refresh ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        status = None if self._status_filter.get() == "All" else self._status_filter.get()
        dept = None if self._dept_filter.get() == "All" else self._dept_filter.get()
        search = self._search_var.get() or None

        try:
            tasks = _load_tasks(status=status, department=dept, search=search)
            stats = _load_stats()
            handoffs = _load_handoffs()
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load data:\n{exc}")
            return

        # Metrics
        for key, vl in self._metric_labels.items():
            val = stats.get(key, "—")
            vl.configure(text=f"{val}{'%' if key == 'pass_rate' else ''}")

        # Handoffs
        for state, lbl in self._handoff_labels.items():
            lbl.configure(text=str(handoffs.get(state, 0)))

        # Table
        for row in self._tree.get_children():
            self._tree.delete(row)

        for t in tasks:
            sid = t.get("status", "draft")
            priority = t.get("priority", 2)
            score = t.get("score")
            score_str = f"{score:.0f}" if isinstance(score, (int, float)) else "—"
            updated = t.get("updated_at") or t.get("created_at") or ""
            updated_str = updated[:16] if updated else ""

            goal = (t.get("goal") or "")[:80]
            dept = t.get("current_department", "—")
            task_type = t.get("task_type", "—")

            row_id = self._tree.insert("", "end", values=(
                t["id"], goal, dept, task_type,
                sid.replace("_", " ").title(),
                PRIORITY_LABELS.get(priority, "—"),
                score_str, updated_str,
            ))
            self._tree.set(row_id, "status", sid)  # hidden tag for color

        # Schedule next refresh
        if self._auto_refresh_id:
            self.after_cancel(self._auto_refresh_id)
        self._auto_refresh_id = self.after(30_000, self.refresh)

    # ── Actions ───────────────────────────────────────────────────────────────

    def _run_selected(self) -> None:
        if not self._selected_task_id:
            messagebox.showwarning("No selection", "Please select a task first.")
            return
        if messagebox.askyesno("Run Task", f"Run task {self._selected_task_id[:8]}…?"):
            result = _run_task(self._selected_task_id)
            if result.get("ok"):
                messagebox.showinfo("Started", result.get("message", "Task started."))
                self.refresh()
            else:
                messagebox.showerror("Error", result.get("error", "Unknown error"))

    def _cancel_selected(self) -> None:
        if not self._selected_task_id:
            messagebox.showwarning("No selection", "Please select a task first.")
            return
        if messagebox.askyesno("Cancel Task", f"Cancel task {self._selected_task_id[:8]}…?"):
            result = _cancel_task(self._selected_task_id)
            if result.get("ok"):
                messagebox.showinfo("Cancelled", "Task cancelled.")
                self.refresh()
            else:
                messagebox.showerror("Error", result.get("error", "Unknown error"))

    def _show_create_dialog(self) -> None:
        dlg = CreateTaskDialog(self, self)
        self.wait_window(dlg)
        if dlg.created:
            self.refresh()

    def _show_task_detail(self) -> None:
        if not self._selected_task_id:
            messagebox.showwarning("No selection", "Please select a task first.")
            return
        self._detail.load_task(self._selected_task_id)

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="agentai_tasks.csv",
        )
        if not path:
            return
        try:
            n = _export_csv(path)
            messagebox.showinfo("Export", f"Exported {n} tasks to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Task Detail Panel
# ──────────────────────────────────────────────────────────────────────────────

class TaskDetailPanel:
    def __init__(self, parent: ttk.Frame, app: AgencyDesktopApp) -> None:
        self.app = app
        self.frame = ttk.Frame(parent, style="Panel.TFrame", padding=(14, 10))
        self.frame.grid_columnconfigure(0, weight=1)
        self._task_id: str | None = None

        # Header
        self._header = tk.Label(
            self.frame, text="Select a task to view details",
            bg=app.C["panel"], fg=app.C["muted"],
            font=("Segoe UI", 10), anchor="w",
        )
        self._header.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        # Status badge
        self._status_lbl = tk.Label(self.frame, text="", bg=app.C["panel2"],
                                    fg="#fff", font=("Segoe UI Semibold", 9),
                                    padx=8, pady=2)
        self._status_lbl.grid(row=1, column=0, sticky="w", pady=(0, 8))

        # Content
        self._content = tk.Frame(self.frame, bg=app.C["panel"])
        self._content.grid(row=2, column=0, sticky="nsew")
        self.frame.grid_rowconfigure(2, weight=1)

        self._score_lbl = tk.Label(self._content, text="", bg=app.C["panel"],
                                    fg=app.C["accent"], font=("Segoe UI Semibold", 18),
                                    anchor="w")
        self._score_lbl.pack(anchor="w", pady=(0, 4))

        self._desc_lbl = tk.Label(self._content, text="", bg=app.C["panel"],
                                   fg=app.C["muted"], font=("Segoe UI", 9),
                                   wraplength=280, anchor="w", justify="left")
        self._desc_lbl.pack(anchor="w", pady=(0, 6))

        self._meta_lbl = tk.Label(self._content, text="", bg=app.C["panel"],
                                   fg=app.C["muted"], font=("Segoe UI", 9),
                                   anchor="w", justify="left")
        self._meta_lbl.pack(anchor="w", pady=(0, 8))

        tk.Label(self._content, text="Review History", bg=app.C["panel"],
                 fg=app.C["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(4, 4))
        self._history_box = tk.Text(self._content, bg=app.C["panel2"],
                                      fg=app.C["text"], font=("Consolas", 9),
                                      relief="flat", state="disabled",
                                      width=40, height=12, wrap="word")
        self._history_box.pack(fill="both", expand=True)

    def load_task(self, task_id: str) -> None:
        self._task_id = task_id
        try:
            from src.db.connection import get_db
            db = get_db()
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                self._header.configure(text=f"Task not found: {task_id[:8]}")
                return
            t = dict(row)
            history = _load_review_history(task_id)
        except Exception as exc:
            self._header.configure(text=f"Error: {exc}")
            return

        # Header
        goal = t.get("goal", "")[:60]
        self._header.configure(
            text=goal, fg=self.app.C["text"],
            font=("Segoe UI Semibold", 11))

        # Status badge
        sid = t.get("status", "draft")
        color = STATUS_COLORS.get(sid, "#94a3b8")
        self._status_lbl.configure(
            text=f"  {sid.replace('_',' ').title()}  ",
            bg=color)

        # Score
        score = t.get("score")
        if isinstance(score, (int, float)) and score > 0:
            self._score_lbl.configure(text=f"Score: {score:.1f} / 100")
        else:
            self._score_lbl.configure(text="Score: —")

        # Description
        desc = t.get("description", "") or ""
        self._desc_lbl.configure(text=desc[:300] + ("…" if len(desc) > 300 else ""))

        # Metadata
        meta_parts = []
        for key in ["current_department", "task_type", "priority", "campaign_id",
                    "account_id", "created_at", "started_at", "completed_at"]:
            val = t.get(key)
            if val:
                meta_parts.append(f"{key}: {val}")
        self._meta_lbl.configure(text="\n".join(meta_parts[:8]))

        # Review history
        self._history_box.configure(state="normal")
        self._history_box.delete("1.0", "end")
        if history:
            for h in history:
                decision = h.get("decision", "—")
                score_v = h.get("score")
                feedback = h.get("feedback", "")[:120]
                ts = h.get("created_at", "")[:19]
                self._history_box.insert("end",
                    f"[{ts}]\n  {decision} — {score_v:.1f}\n  {feedback}\n\n")
        else:
            self._history_box.insert("end", "No review history yet.\n")
        self._history_box.configure(state="disabled")


# ──────────────────────────────────────────────────────────────────────────────
# Create Task Dialog
# ──────────────────────────────────────────────────────────────────────────────

class CreateTaskDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, app: AgencyDesktopApp) -> None:
        super().__init__(parent)
        self.app = app
        self.created = False
        self.title("Create New Task")
        self.geometry("560x620")
        self.resizable(False, False)
        self.configure(bg=app.C["bg"])
        self.grab_set()

        outer = ttk.Frame(self, style="App.TFrame", padding=(20, 16))
        outer.pack(fill="both", expand=True)

        # Title
        tk.Label(outer, text="Create New Task", bg=app.C["bg"],
                 fg=app.C["text"], font=("Segoe UI Semibold", 16)).pack(
                     anchor="w", pady=(0, 16))

        fields = [
            ("Goal *", "goal"),
            ("Description", "description"),
        ]

        self._vars: dict[str, tk.StringVar] = {}
        for label, key in fields:
            f = tk.Frame(outer, bg=app.C["panel"])
            f.pack(fill="x", pady=(0, 10))
            tk.Label(f, text=label, bg=app.C["panel"], fg=app.C["muted"],
                     font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=10, pady=(8, 4))
            var = tk.StringVar()
            self._vars[key] = var
            ent = tk.Entry(f, textvariable=var, bg=app.C["panel2"],
                            fg=app.C["text"], font=("Segoe UI", 10),
                            insertbackground="white", relief="flat")
            ent.pack(fill="x", padx=10, pady=(0, 8))

        # Dept + Type row
        row2 = tk.Frame(outer, bg=app.C["bg"])
        row2.pack(fill="x", pady=(0, 10))
        for label, key, values in [
            ("Department", "department", DEPARTMENTS),
            ("Task Type", "task_type", TASK_TYPES),
        ]:
            f = tk.Frame(row2, bg=app.C["panel"])
            f.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(f, text=label, bg=app.C["panel"], fg=app.C["muted"],
                     font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=10, pady=(8, 4))
            var = tk.StringVar(value=values[0])
            self._vars[key] = var
            cb = ttk.Combobox(f, values=values, textvariable=var,
                               state="readonly", font=("Segoe UI", 10))
            cb.current(0)
            cb.pack(fill="x", padx=10, pady=(0, 8))

        # Priority
        f = tk.Frame(outer, bg=app.C["panel"])
        f.pack(fill="x", pady=(0, 10))
        tk.Label(f, text="Priority", bg=app.C["panel"], fg=app.C["muted"],
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=10, pady=(8, 4))
        self._priority_var = tk.IntVar(value=2)
        for i, (val, label) in enumerate(PRIORITY_LABELS.items()):
            tk.Radiobutton(f, text=label, variable=self._priority_var,
                           value=val, bg=app.C["panel"], fg=app.C["text"],
                           font=("Segoe UI", 10),
                           activebackground=app.C["panel"]).pack(
                               side="left", padx=(8, 12), pady=(0, 8))

        # KPIs
        f = tk.Frame(outer, bg=app.C["panel"])
        f.pack(fill="x", pady=(0, 16))
        tk.Label(f, text="KPIs (JSON, optional)", bg=app.C["panel"], fg=app.C["muted"],
                 font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=10, pady=(8, 4))
        self._kpis_var = tk.StringVar(value='{"roas": 3.0, "ctr": 2.0}')
        ent = tk.Entry(f, textvariable=self._kpis_var, bg=app.C["panel2"],
                        fg=app.C["text"], font=("Consolas", 10),
                        insertbackground="white", relief="flat")
        ent.pack(fill="x", padx=10, pady=(0, 8))

        # Buttons
        btn_row = tk.Frame(outer, bg=app.C["bg"])
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="Create Task", style="Primary.TButton",
                   command=self._submit).pack(side="right")

    def _submit(self) -> None:
        goal = self._vars["goal"].get().strip()
        if not goal:
            messagebox.showwarning("Required", "Goal is required.")
            return
        try:
            kpis = json.loads(self._kpis_var.get()) if self._kpis_var.get().strip() else {}
        except json.JSONDecodeError:
            messagebox.showerror("Invalid JSON", "KPIs must be valid JSON.")
            return
        try:
            task_id = _create_task(
                goal=goal,
                description=self._vars["description"].get(),
                task_type=self._vars["task_type"].get(),
                department=self._vars["department"].get(),
                priority=self._priority_var.get(),
                kpis=kpis,
            )
            self.created = True
            messagebox.showinfo("Created", f"Task created:\n{task_id[:36]}")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s")
    app = AgencyDesktopApp()
    app.mainloop()
