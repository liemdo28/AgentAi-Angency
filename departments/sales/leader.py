from models import Leader

LEADER = Leader(
    id="sales_leader_01",
    full_name="SalesLead",
    role="Sales Lead",
    department="sales",
    responsibilities=(
        "Duyệt pricing theo policy finance.",
        "Quản trị pipeline và forecast.",
        "Đảm bảo target doanh thu mới.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
