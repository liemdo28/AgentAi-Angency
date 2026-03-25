from models import Leader

LEADER = Leader(
    id="finance_leader_01",
    full_name="FinanceLead",
    role="Finance Lead",
    department="finance",
    responsibilities=(
        "Duyệt ngân sách campaign/project.",
        "Phê duyệt mức giảm giá theo rule.",
        "Chịu trách nhiệm lợi nhuận công ty.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
