from models import Leader

LEADER = Leader(
    id="media_leader_01",
    full_name="MediaLead",
    role="Media Lead",
    department="media",
    responsibilities=(
        "Duyệt kế hoạch phân bổ ngân sách.",
        "Ra quyết định scale theo dữ liệu.",
        "Báo cáo hiệu quả đến Account/Data.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
