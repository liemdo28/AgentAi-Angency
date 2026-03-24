from models import Leader

LEADER = Leader(
    id="data_leader_01",
    full_name="DataLead",
    role="Data Lead",
    department="data",
    responsibilities=(
        "Duyệt data model và metric definition.",
        "Giám sát chất lượng dữ liệu.",
        "Phát hành insight/action plan cho team.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
