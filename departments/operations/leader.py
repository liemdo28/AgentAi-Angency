from models import Leader

LEADER = Leader(
    id="operations_leader_01",
    full_name="OperationsLead",
    role="Operations Lead",
    department="operations",
    responsibilities=(
        "Duyệt phân bổ nguồn lực.",
        "Quản lý quy trình nội bộ.",
        "Tối ưu hiệu suất vận hành.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
