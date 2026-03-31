"""Desktop dashboard for AgentAI Agency.

Run:
    python src/windows_app.py
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont


class AgencyDesktopApp(tk.Tk):
    """Modern, responsive Windows desktop interface for AgentAI Agency."""

    def __init__(self) -> None:
        super().__init__()
        self.title("AgentAI Agency — Desktop Console")
        self.geometry("1280x800")
        self.minsize(1024, 640)

        self.base_font = tkfont.nametofont("TkDefaultFont")
        self.base_font.configure(family="Segoe UI", size=10)

        self._build_style()
        self._build_layout()
        self.bind("<Configure>", self._on_resize)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        self.colors = {
            "bg": "#f4f6fb",
            "panel": "#ffffff",
            "text": "#1c2434",
            "muted": "#647089",
            "primary": "#2d6cea",
            "success": "#1ea672",
            "warning": "#f59e0b",
            "border": "#d9dfeb",
        }

        self.configure(bg=self.colors["bg"])

        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Panel.TFrame", background=self.colors["panel"], relief="flat")
        style.configure(
            "Title.TLabel",
            background=self.colors["bg"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 19),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.colors["bg"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "PanelTitle.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "Metric.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["text"],
            font=("Segoe UI Semibold", 22),
        )
        style.configure(
            "Caption.TLabel",
            background=self.colors["panel"],
            foreground=self.colors["muted"],
            font=("Segoe UI", 10),
        )
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(12, 8))
        style.configure("Primary.TButton", background=self.colors["primary"], foreground="white")
        style.map(
            "Primary.TButton",
            background=[("active", "#1f57c2")],
            foreground=[("disabled", "#f5f7ff")],
        )

        style.configure(
            "Treeview",
            font=("Segoe UI", 10),
            rowheight=34,
            fieldbackground=self.colors["panel"],
            bordercolor=self.colors["border"],
        )
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 10),
            background="#eef2fb",
            foreground=self.colors["text"],
            relief="flat",
        )
        style.map("Treeview", background=[("selected", "#dbe8ff")], foreground=[("selected", self.colors["text"])])

    def _build_layout(self) -> None:
        container = ttk.Frame(self, style="App.TFrame", padding=(20, 16))
        container.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container.grid_rowconfigure(2, weight=1)
        container.grid_columnconfigure(0, weight=4)
        container.grid_columnconfigure(1, weight=2)

        ttk.Label(container, text="AgentAI Agency Desktop", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            container,
            text="Professional workflow dashboard optimized for 720p to 4K displays",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        self._build_task_panel(container)
        self._build_side_panel(container)

    def _build_task_panel(self, parent: ttk.Frame) -> None:
        task_panel = ttk.Frame(parent, style="Panel.TFrame", padding=(16, 14))
        task_panel.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        parent.grid_rowconfigure(2, weight=1)

        task_panel.grid_rowconfigure(2, weight=1)
        task_panel.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(task_panel, style="Panel.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ttk.Label(header, text="Task Pipeline", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Create New Task", style="Primary.TButton").grid(row=0, column=1, sticky="e")

        filter_row = ttk.Frame(task_panel, style="Panel.TFrame")
        filter_row.grid(row=1, column=0, sticky="ew", pady=(12, 10))
        filter_row.grid_columnconfigure(1, weight=1)

        ttk.Label(filter_row, text="Search", style="Caption.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_row, textvariable=self.search_var)
        search_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(filter_row, text="Refresh").grid(row=0, column=2, padx=(8, 0))

        columns = ("id", "goal", "department", "status", "score", "updated")
        tree = ttk.Treeview(task_panel, columns=columns, show="headings")
        tree.grid(row=2, column=0, sticky="nsew")

        headings = {
            "id": "Task ID",
            "goal": "Goal",
            "department": "Department",
            "status": "Status",
            "score": "Score",
            "updated": "Updated",
        }
        widths = {"id": 140, "goal": 340, "department": 120, "status": 120, "score": 90, "updated": 140}

        for col in columns:
            tree.heading(col, text=headings[col])
            anchor = "w" if col in {"goal", "department"} else "center"
            tree.column(col, width=widths[col], anchor=anchor, stretch=(col == "goal"))

        demo_rows = [
            ("a1f2…", "Create Q2 launch campaign", "Creative", "RUNNING", "97", "10:42"),
            ("d9e8…", "Build B2B lead list", "Sales", "REVIEW", "98", "10:19"),
            ("k3n7…", "Audit ad spend efficiency", "Account", "DONE", "99", "09:56"),
            ("z5p1…", "Competitive market research", "Strategy", "WAITING", "95", "09:27"),
        ]
        for row in demo_rows:
            tree.insert("", tk.END, values=row)

        y_scroll = ttk.Scrollbar(task_panel, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y_scroll.set)
        y_scroll.grid(row=2, column=1, sticky="ns")

    def _build_side_panel(self, parent: ttk.Frame) -> None:
        side = ttk.Frame(parent, style="App.TFrame")
        side.grid(row=2, column=1, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)

        metrics = [
            ("Active Tasks", "42", self.colors["primary"]),
            ("Leader Pass Rate", "98.4%", self.colors["success"]),
            ("Needs Review", "6", self.colors["warning"]),
        ]

        for idx, (label, value, accent) in enumerate(metrics):
            card = ttk.Frame(side, style="Panel.TFrame", padding=(14, 12))
            card.grid(row=idx, column=0, sticky="ew", pady=(0, 10))
            tk.Frame(card, bg=accent, width=4, height=58).grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
            ttk.Label(card, text=value, style="Metric.TLabel").grid(row=0, column=1, sticky="w")
            ttk.Label(card, text=label, style="Caption.TLabel").grid(row=1, column=1, sticky="w")

        actions = ttk.Frame(side, style="Panel.TFrame", padding=(14, 12))
        actions.grid(row=3, column=0, sticky="nsew")
        side.grid_rowconfigure(3, weight=1)

        ttk.Label(actions, text="Quick Actions", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Button(actions, text="Open API Docs").grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Run Overdue Scan").grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Export Report").grid(row=3, column=0, sticky="ew")

    def _on_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return

        width = max(self.winfo_width(), 1024)
        scale = max(0.90, min(1.65, width / 1280))

        ttk.Style().configure("Title.TLabel", font=("Segoe UI Semibold", int(19 * scale)))
        ttk.Style().configure("Subtitle.TLabel", font=("Segoe UI", max(10, int(10 * scale))))
        ttk.Style().configure("PanelTitle.TLabel", font=("Segoe UI Semibold", max(11, int(12 * scale))))
        ttk.Style().configure("Metric.TLabel", font=("Segoe UI Semibold", max(18, int(22 * scale))))
        ttk.Style().configure("Caption.TLabel", font=("Segoe UI", max(9, int(10 * scale))))
        ttk.Style().configure("TButton", font=("Segoe UI Semibold", max(9, int(10 * scale))))
        ttk.Style().configure("Treeview", font=("Segoe UI", max(9, int(10 * scale))), rowheight=max(28, int(34 * scale)))


if __name__ == "__main__":
    app = AgencyDesktopApp()
    app.mainloop()
