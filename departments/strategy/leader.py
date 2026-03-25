from models import Leader

LEADER = Leader(
    id="strategy_leader_01",
    full_name="StrategyLead",
    role="Strategy Lead",
    department="strategy",
    responsibilities=(
        "Duyệt strategic direction.",
        "Phê duyệt hypothesis testing plan.",
        "Đảm bảo alignment với business goal.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
