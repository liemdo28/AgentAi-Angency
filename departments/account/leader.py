from models import Leader

LEADER = Leader(
    id="account_leader_01",
    full_name="AccountManager",
    role="Account Manager",
    department="account",
    responsibilities=(
        "Duyệt scope và proposal.",
        "Duyệt báo cáo tuần/tháng gửi khách hàng.",
        "Chịu trách nhiệm retention/upsell.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
