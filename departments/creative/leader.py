from models import Leader

LEADER = Leader(
    id="creative_leader_01",
    full_name="CreativeLead",
    role="Creative Lead",
    department="creative",
    responsibilities=(
        "Duyệt guideline hình ảnh và nội dung.",
        "Ưu tiên backlog sáng tạo theo data feedback.",
        "Đảm bảo chất lượng output cuối.",
    ),
    approval_scope=(
        "workflow_handoff",
        "kpi_review",
        "resource_decision",
    ),
)
