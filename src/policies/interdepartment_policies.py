from __future__ import annotations

from models import HandoffPolicy

# Chính sách handoff giữa các phòng ban theo workflow end-to-end.
POLICIES: tuple[HandoffPolicy, ...] = (
    HandoffPolicy("sales", "account", ("lead_profile", "deal_status", "target_kpi"), ("project_brief", "kickoff_schedule"), 8, "Account Manager"),
    HandoffPolicy("account", "strategy", ("project_brief", "client_constraints", "budget"), ("strategy_direction", "funnel_plan"), 12, "Strategy Lead"),
    HandoffPolicy("strategy", "creative", ("strategy_direction", "key_message", "persona"), ("creative_concept", "content_plan"), 24, "Creative Lead"),
    HandoffPolicy("strategy", "media", ("funnel_plan", "audience_hypothesis", "budget"), ("media_plan", "channel_split"), 24, "Media Lead"),
    HandoffPolicy("creative", "account", ("draft_assets", "copy_variants"), ("client_review_package",), 8, "Account Manager"),
    HandoffPolicy("account", "creative", ("client_feedback", "revision_priority"), ("revised_assets",), 8, "Creative Lead"),
    HandoffPolicy("creative", "media", ("approved_assets", "creative_notes"), ("ad_ready_assets",), 4, "Media Lead"),
    HandoffPolicy("account", "tech", ("tracking_requirements", "landing_scope"), ("technical_implementation_plan",), 8, "Tech Lead"),
    HandoffPolicy("tech", "media", ("landing_page_url", "tracking_tags"), ("launch_checklist",), 4, "Media Lead"),
    HandoffPolicy("tech", "data", ("event_schema", "tracking_logs"), ("validated_tracking_map",), 6, "Data Lead"),
    HandoffPolicy("data", "media", ("performance_dashboard", "anomaly_alerts"), ("optimization_actions",), 6, "Media Lead"),
    HandoffPolicy("data", "account", ("weekly_metrics", "insights"), ("client_report",), 12, "Account Manager"),
    HandoffPolicy("media", "creative", ("winning_ad_set", "underperforming_creatives"), ("new_variants",), 12, "Creative Lead"),
    HandoffPolicy("production", "creative", ("raw_footage", "photo_assets"), ("editable_asset_pack",), 16, "Creative Lead"),
    HandoffPolicy("operations", "finance", ("resource_plan", "vendor_costs"), ("approved_budget",), 24, "Finance Lead"),
    HandoffPolicy("finance", "account", ("approved_budget", "margin_constraints"), ("billable_scope",), 8, "Account Manager"),
    HandoffPolicy("account", "operations", ("staffing_requirements", "timeline"), ("resource_allocation",), 12, "Operations Lead"),
    HandoffPolicy("media", "sales", ("campaign_success_cases", "roi_summary"), ("sales_enablement_material",), 24, "Sales Lead"),
    HandoffPolicy("sales", "operations", ("forecast_pipeline", "expected_onboarding"), ("capacity_plan",), 24, "Operations Lead"),
    HandoffPolicy("data", "finance", ("revenue_actual", "profit_by_channel"), ("financial_review",), 24, "Finance Lead"),
    HandoffPolicy("finance", "sales", ("pricing_floor", "discount_rules"), ("deal_pricing_policy",), 24, "Sales Lead"),
    # Missing critical loops filled
    HandoffPolicy("media", "account", ("pacing_report", "risk_flags"), ("client_status_update",), 8, "Account Manager"),
    HandoffPolicy("creative", "production", ("storyboard", "shooting_script"), ("production_shotlist",), 8, "Production Lead"),
    HandoffPolicy("account", "finance", ("billing_milestones", "contract_terms"), ("invoice_plan",), 8, "Finance Lead"),
    HandoffPolicy("data", "strategy", ("insight_report", "cohort_analysis"), ("strategy_refresh",), 16, "Strategy Lead"),
    HandoffPolicy("tech", "operations", ("release_notes", "incident_risk"), ("ops_impact_plan",), 8, "Operations Lead"),
    # CRM/Automation integration
    HandoffPolicy("data", "crm_automation", ("customer_segments", "behavior_events"), ("trigger_rules",), 12, "CRM Automation Lead"),
    HandoffPolicy("crm_automation", "media", ("retention_audience", "lifecycle_offer"), ("remarketing_brief",), 12, "Media Lead"),
    HandoffPolicy("crm_automation", "account", ("retention_performance", "churn_alert"), ("client_retention_update",), 12, "Account Manager"),
)
