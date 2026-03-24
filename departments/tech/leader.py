from models import Leader

LEADER = Leader(
    id="tech_leader_01",
    full_name="TechLead",
    role="Tech Lead",
    department="tech",
    responsibilities=(
        "Duyệt kiến trúc kỹ thuật.",
        "Đảm bảo uptime và performance.",
        "Quản lý release và rollback plan.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
