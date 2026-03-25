from models import Leader

LEADER = Leader(
    id="crm_leader_01",
    full_name="CRMAutomationLead",
    role="CRM Automation Lead",
    department="crm_automation",
    responsibilities=(
        "Duyệt architecture automation flow.",
        "Chịu trách nhiệm LTV/retention uplift.",
        "Kết nối CRM với Data/Media/Account.",
    ),
    approval_scope=(
        "automation_release",
        "segment_policy",
        "retention_kpi_review",
    ),
)
