from models import Leader

LEADER = Leader(
    id="production_leader_01",
    full_name="ProductionLead",
    role="Production Lead",
    department="production",
    responsibilities=(
        "Duyệt lịch sản xuất.",
        "Đảm bảo SLA bàn giao asset.",
        "Kiểm soát chất lượng hậu kỳ.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
