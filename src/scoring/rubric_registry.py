"""
Rubric Registry — per-department scoring rubrics with detailed checklists.
11 departments, each with 4 criteria (completeness, accuracy, actionability, professional quality).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RubricCriterion:
    name: str
    weight: float          # 0.0 – 1.0
    description: str
    checklist: list[str]   # items the LLM checks
    max_score: float = 100.0


@dataclass
class Rubric:
    department: str
    task_types: tuple[str, ...]
    criteria: list[RubricCriterion]
    min_acceptable_score: float = 60.0
    quality_threshold: float = 98.0
    notes: str = ""


# ── Rubric Definitions ──────────────────────────────────────────────────────

RUBRIC_DEFINITIONS: dict[str, Rubric] = {

    # ── 1. Strategy ────────────────────────────────────────────────────────
    "strategy": Rubric(
        department="strategy",
        task_types=("new_campaign", "ad_hoc"),
        notes="Strategic recommendations must be backed by data, competitive context, and clear rationale.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="All required sections present and fully fleshed out",
                checklist=[
                    "SWOT analysis covers all four quadrants with specific evidence",
                    "Market sizing includes TAM, SAM, SOM with sources cited",
                    "Competitor analysis names at least 3 real competitors with positioning notes",
                    "Target audience has demographic AND psychographic AND behavioral data",
                    "Budget allocation adds up to 100% with clear rationale per channel",
                    "Timeline includes specific milestones and decision gates",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.30,
                description="Data, facts, and figures are plausible and internally consistent",
                checklist=[
                    "No internal contradictions between sections",
                    "Market size numbers are within reasonable industry ranges",
                    "Budget figures are proportional to stated market size",
                    "Timeline is feasible given team size and scope",
                    "No hallucinated statistics or unsourced claims",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.30,
                description="Recommendations are specific enough to execute immediately",
                checklist=[
                    "Each recommendation has a clear owner and deadline",
                    "Channel strategy explains WHY each channel was chosen (not just listed)",
                    "Audience definition includes specific platforms/media they consume",
                    "KPIs are measurable and tied to business outcomes",
                    "Budget split includes rationale based on expected ROAS per channel",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Presentation quality appropriate for C-suite client delivery",
                checklist=[
                    "Structure follows clear hierarchy with executive summary first",
                    "Language is professional, unambiguous, free of jargon overload",
                    "Charts/tables are referenced and labelled",
                    "Sources and data dates are cited where applicable",
                ],
            ),
        ],
    ),

    # ── 2. Creative ───────────────────────────────────────────────────────
    "creative": Rubric(
        department="creative",
        task_types=("creative_brief", "new_campaign"),
        notes="Creative output must be on-brand, differentiated, and executable.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="All creative elements delivered as specified in brief",
                checklist=[
                    "Headlines (minimum 3 variants with different emotional angles)",
                    "Body copy that expands on headline without repeating it verbatim",
                    "Visual direction or description is specific (not generic stock advice)",
                    "CTA is clear, specific, and appropriate to the channel",
                    "All required formats/sizes requested are addressed",
                    "Taglines that could work across multiple executions provided",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.20,
                description="Copy is grammatically correct, on-brand, factually accurate",
                checklist=[
                    "No grammatical, spelling, or punctuation errors",
                    "Tone matches brand voice as described in brief",
                    "Factual claims in copy are verifiable",
                    "Character counts respect platform limits",
                    "Hashtags and handles are correctly formatted",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.35,
                description="Creative is ready for production or minimal revision",
                checklist=[
                    "Copy can be handed directly to designer/copywriter for production",
                    "Visual direction is specific enough to brief a photographer/illustrator",
                    "A/B test variants are meaningfully different (not just word swaps)",
                    "Platform adaptations are noted for each required format",
                    "Any required legal/regulatory copy is included",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.20,
                description="Creative is compelling, differentiated, and brand-appropriate",
                checklist=[
                    "Headline is strong enough to stop scroll or capture attention",
                    "Copy has a clear logical flow: hook -> benefit -> proof -> CTA",
                    "Creative shows clear differentiation from competitors",
                    "Emotional appeal is appropriate to brand and audience",
                    "Output does not feel templated or formulaic",
                ],
            ),
        ],
    ),

    # ── 3. Media ─────────────────────────────────────────────────────────
    "media": Rubric(
        department="media",
        task_types=("new_campaign", "ad_hoc"),
        notes="Media plans must include specific placements, targeting parameters, and budget math.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="Full media plan with all required elements",
                checklist=[
                    "Channel list with specific platforms and ad formats",
                    "Targeting parameters for each placement (demo, interest, behavioral)",
                    "Budget allocation per channel with percentage and dollar amounts",
                    "Flight schedule with start/end dates and pacing curve",
                    "KPI targets per channel (CPM, CPC, CPA, ROAS as applicable)",
                    "Competitor spend estimates or benchmark data included",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.30,
                description="Numbers are internally consistent and benchmark-aligned",
                checklist=[
                    "Budget totals match across all sections",
                    "CPM/CPC estimates are within reasonable industry ranges for the market",
                    "Audience size estimates are proportional to stated TAM",
                    "Pacing math is consistent (impressions = budget/CPM * 1000)",
                    "No placeholder numbers or '(TBD)' without justification",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.30,
                description="Plan can be loaded into platform without further research",
                checklist=[
                    "Each platform has specific campaign setup instructions or platform name",
                    "Audience segments are implementable (not vague 'high-income urban')",
                    "Bidding strategy is specified with rationale",
                    "Creative specs for each format are noted",
                    "Frequency cap recommendation is justified",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Plan is structured, readable, and client-ready",
                checklist=[
                    "Executive summary precedes detailed plan",
                    "All tables are labelled with units (%, $, CPM, etc.)",
                    "Assumptions are stated explicitly",
                    "Sources for benchmarks are cited",
                ],
            ),
        ],
    ),

    # ── 4. Data ──────────────────────────────────────────────────────────
    "data": Rubric(
        department="data",
        task_types=("data_report", "ad_hoc"),
        notes="Data reports must be accurate, well-structured, and include actionable interpretation.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.30,
                description="All requested metrics and breakdowns present",
                checklist=[
                    "All KPIs requested in the brief are reported",
                    "Data covers the full requested time period",
                    "Breakdowns by channel/audience/creative are included where relevant",
                    "Comparison period (vs last period) is included",
                    "Methodology section explains how metrics were calculated",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.35,
                description="Numbers are correct and calculations are transparent",
                checklist=[
                    "No formula errors in derived metrics (ROAS, CTR, CPA, etc.)",
                    "Data source is identified and credible",
                    "No data gaps or missing days are unexplained",
                    "Percentages add up correctly",
                    "Time period boundaries are consistent",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.20,
                description="Analysis goes beyond raw numbers to provide insight",
                checklist=[
                    "Each major metric change has an explanatory note",
                    "Winners and losers are identified with specific campaign/creative names",
                    "Recommendations are specific and tied to data findings",
                    "Next reporting period actions are outlined",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Visualisation and presentation are clear and professional",
                checklist=[
                    "Charts are labelled with titles, axes, and legends",
                    "Key numbers are highlighted or called out",
                    "Report can be understood by a non-technical stakeholder",
                    "Sources and data dates are clearly cited",
                ],
            ),
        ],
    ),

    # ── 5. Account ───────────────────────────────────────────────────────
    "account": Rubric(
        department="account",
        task_types=("ad_hoc", "retention_campaign"),
        notes="Account management outputs should be professional, client-facing, and relationship-focused.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="All required client communication elements present",
                checklist=[
                    "Status update covers all active campaigns",
                    "Action items have clear owners and deadlines",
                    "Risks and blockers are surfaced honestly",
                    "Financial summary (spend vs budget) included",
                    "Next steps section is specific, not generic",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.30,
                description="All data cited is correct and attributable",
                checklist=[
                    "Campaign metrics match actual platform data",
                    "Budget figures are accurate to the cent",
                    "No over-promising on results",
                    "Dates and timelines are accurate",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.30,
                description="Client can act on every item without follow-up questions",
                checklist=[
                    "Each question raised by client has a specific answer",
                    "Decisions required from client are clearly labelled",
                    "Escalations include proposed solutions, not just problems",
                    "Contract/budget change requests have clear financial impact",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Communication is polished, tone-appropriate, client-first",
                checklist=[
                    "Tone is professional, warm, and confident",
                    "Jargon is minimized or explained for non-marketers",
                    "Layout is clean and easy to scan",
                    "No typos or formatting errors",
                ],
            ),
        ],
    ),

    # ── 6. Tech ──────────────────────────────────────────────────────────
    "tech": Rubric(
        department="tech",
        task_types=("ad_hoc",),
        notes="Technical outputs must be accurate, secure, and production-ready.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="All required technical components delivered",
                checklist=[
                    "Code/module solves the stated problem end-to-end",
                    "Configuration files are complete and annotated",
                    "API integration includes error handling",
                    "Documentation covers setup, usage, and edge cases",
                    "Tests or validation steps are provided",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.35,
                description="Code is syntactically correct and logic is sound",
                checklist=[
                    "Code runs without syntax errors",
                    "API calls use correct endpoints and auth methods",
                    "No hardcoded secrets or credentials",
                    "Error handling covers all failure modes",
                    "Dependencies are specified with compatible versions",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.25,
                description="Output can be deployed or integrated with minimal guidance",
                checklist=[
                    "Deployment steps are step-by-step and non-ambiguous",
                    "Environment variables are documented",
                    "Required permissions/roles are stated",
                    "Rollback procedure is included for risky changes",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Code is clean, readable, and follows best practices",
                checklist=[
                    "Variable and function names are descriptive",
                    "Comments explain WHY, not just WHAT",
                    "No commented-out dead code",
                    "Follows language/framework conventions",
                ],
            ),
        ],
    ),

    # ── 7. Sales ─────────────────────────────────────────────────────────
    "sales": Rubric(
        department="sales",
        task_types=("ad_hoc",),
        notes="Sales materials must be persuasive, credible, and prospect-specific.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="All pitch components included",
                checklist=[
                    "Problem statement is specific to the prospect's industry/situation",
                    "Agency/value proposition is clearly articulated",
                    "Case studies include specific metrics and client names (or anonymised)",
                    "Team introduction is included",
                    "Pricing/engagement model is outlined",
                    "CTA is clear and specific",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.30,
                description="Claims are verifiable and not overstated",
                checklist=[
                    "Case study results are realistic and sourced",
                    "No unsubstantiated 'best in class' or 'number one' claims",
                    "Pricing is realistic for the market",
                    "Timeline claims are feasible",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.30,
                description="Sales team can use the material without adaptation",
                checklist=[
                    "Talking points are concise and memorable",
                    "Objection responses are pre-prepared for likely blockers",
                    "Follow-up materials (deck, one-pager) are referenced",
                    "Meeting agenda or next steps are clear",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Materials are polished and reflect agency brand",
                checklist=[
                    "Design is consistent with agency branding",
                    "Language is confident but not arrogant",
                    "Length is appropriate to the sales stage",
                    "No grammar or spelling errors",
                ],
            ),
        ],
    ),

    # ── 8. Operations ────────────────────────────────────────────────────
    "operations": Rubric(
        department="operations",
        task_types=("ad_hoc",),
        notes="Operational outputs should be precise, actionable, and workflow-friendly.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.30,
                description="Process or workflow covers all required steps",
                checklist=[
                    "All stakeholders and their roles are identified",
                    "All workflow steps are listed in correct order",
                    "Handoff points and dependencies are marked",
                    "SLA/timeline for each step is specified",
                    "Escalation path is defined for each step",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.30,
                description="Processes are logically sound and feasible",
                checklist=[
                    "No circular dependencies in workflow",
                    "Timelines are realistic given team capacity",
                    "Resource requirements are accurate",
                    "No steps are missing from the process",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.25,
                description="Output can be turned into a SOP or project plan immediately",
                checklist=[
                    "Each step has a clear owner",
                    "Each step has a clear definition of 'done'",
                    "RACI or equivalent is provided for cross-functional steps",
                    "Tools/systems used at each step are named",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Documentation is clear and unambiguous",
                checklist=[
                    "Language is precise (no 'maybe', 'probably', 'as needed')",
                    "Diagrams or flowcharts are described or referenced",
                    "Version and review date are stated",
                    "Exceptions to the process are handled",
                ],
            ),
        ],
    ),

    # ── 9. Finance ───────────────────────────────────────────────────────
    "finance": Rubric(
        department="finance",
        task_types=("ad_hoc", "data_report"),
        notes="Financial outputs must be accurate, auditable, and professionally formatted.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.30,
                description="All required financial elements present",
                checklist=[
                    "Income/expense breakdown by category",
                    "Budget vs actual comparison",
                    "Variance analysis with explanations for variances >5%",
                    "Cash flow projection for the period",
                    "All figures have correct currency and period labels",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.40,
                description="All calculations are correct and internally consistent",
                checklist=[
                    "Totals equal sum of line items",
                    "Percentages add to 100%",
                    "No rounding errors in final totals",
                    "Exchange rates and currency conversions are correct",
                    "Actuals match source documents",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.15,
                description="Report enables decision-making",
                checklist=[
                    "Variances are explained, not just listed",
                    "Budget recommendations are specific",
                    "Cash flow risks are flagged with proposed mitigations",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Formatting follows financial reporting standards",
                checklist=[
                    "Tables use consistent number formatting",
                    "Negative numbers are clearly indicated",
                    "Assumptions are footnoted",
                    "Prepared by / approved by fields present",
                ],
            ),
        ],
    ),

    # ── 10. CRM / CRM Automation ──────────────────────────────────────────
    "crm_automation": Rubric(
        department="crm_automation",
        task_types=("retention_campaign", "creative_brief", "ad_hoc"),
        notes="CRM outputs must be data-driven, personalized, and lifecycle-appropriate.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.25,
                description="Full CRM campaign or automation design delivered",
                checklist=[
                    "Target segment definition with specific criteria",
                    "Lifecycle stage addressed (acquisition/activation/retention/win-back)",
                    "Message hierarchy (subject line, preview text, body, CTA) complete",
                    "Send frequency and timing recommendation included",
                    "Personalization tokens used appropriately",
                    "A/B test plan for subject line and/or content included",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.25,
                description="Contact data and segment logic are sound",
                checklist=[
                    "Segment size estimate is reasonable",
                    "Personalization fields exist in the data model",
                    "No GDPR/CAN-SPAM violations in copy or send logic",
                    "Frequency recommendation is justified (not just 'weekly')",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.30,
                description="Campaign can be set up in the CRM platform immediately",
                checklist=[
                    "Automation flow has each step and decision branch defined",
                    "Trigger conditions are specific (behavioral or time-based)",
                    "Dynamic content rules are specified",
                    "UTM parameters and tracking are configured",
                    "Suppression list logic is defined",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.20,
                description="Copy and design are polished and brand-consistent",
                checklist=[
                    "Subject line is compelling, specific, and under 50 characters",
                    "Preview text complements subject line (not duplicates it)",
                    "Body copy is scannable (short paragraphs, bullet points)",
                    "CTA button/text is specific and action-oriented",
                    "Footer (unsubscribe, physical address) meets legal requirements",
                ],
            ),
        ],
    ),

    # ── 11. Production ──────────────────────────────────────────────────
    "production": Rubric(
        department="production",
        task_types=("creative_brief", "ad_hoc"),
        notes="Production deliverables must be technically spec'd and production-ready.",
        criteria=[
            RubricCriterion(
                name="completeness",
                weight=0.30,
                description="Full production spec for all required assets",
                checklist=[
                    "All required formats/sizes are listed with dimensions",
                    "Technical specs (resolution, colour mode, file format) for each asset",
                    "Copy deck with all required text for each format",
                    "Asset list with clear naming convention",
                    "Review and approval workflow is defined",
                    "Delivery deadline and handoff process specified",
                ],
            ),
            RubricCriterion(
                name="accuracy",
                weight=0.30,
                description="Specs are correct for the intended platforms and media",
                checklist=[
                    "Dimensions match platform requirements exactly",
                    "File formats are correct (not just 'image')",
                    "Colour values are accurate (RGB vs CMYK noted)",
                    "Copy character counts are within platform limits",
                    "Legal/rights requirements are specified",
                ],
            ),
            RubricCriterion(
                name="actionability",
                weight=0.25,
                description="Brief can be handed directly to a production studio or freelancer",
                checklist=[
                    "Visual direction is specific enough to brief a designer",
                    "Creative references/examples are cited",
                    "Brand assets (logo, fonts, guidelines) are linked or attached",
                    "Feedback revision rounds are specified",
                    "Any third-party dependencies (photography, music licensing) are listed",
                ],
            ),
            RubricCriterion(
                name="professional_quality",
                weight=0.15,
                description="Production plan is realistic, efficient, and cost-aware",
                checklist=[
                    "Timeline accounts for review cycles and revisions",
                    "Production cost estimate is included if requested",
                    "Quality control checkpoints are defined",
                    "Deliverable acceptance criteria are clear",
                ],
            ),
        ],
    ),
}


_DEPARTMENT_ALIASES: dict[str, str] = {
    "crm": "crm_automation",
}


def get_rubric(department: str) -> Rubric:
    """Get rubric for a department, defaulting to 'strategy' if unknown."""
    key = department.lower()
    key = _DEPARTMENT_ALIASES.get(key, key)
    rubric = RUBRIC_DEFINITIONS.get(key)
    if rubric is None:
        logger.warning("No rubric for department '%s', using strategy rubric", department)
        rubric = RUBRIC_DEFINITIONS["strategy"]
    return rubric


# Per-task-type threshold overrides.
# Simple tasks need lower threshold; complex tasks keep 98.
_TASK_TYPE_THRESHOLDS: dict[str, float] = {
    "client_reporting": 90.0,
    "data_ingestion": 85.0,
    "ad_hoc": 92.0,
    "campaign_launch": 96.0,
    "campaign_optimization": 94.0,
    "retention_program": 94.0,
    "single_route": 92.0,
}


class RubricRegistry:
    """Registry for accessing all rubrics."""

    def __init__(self) -> None:
        self._rubrics: dict[str, Rubric] = RUBRIC_DEFINITIONS

    def get(self, department: str) -> Rubric:
        return get_rubric(department)

    def list_departments(self) -> list[str]:
        return list(self._rubrics.keys())

    def list_task_types(self, department: str) -> tuple[str, ...]:
        return self.get(department).task_types

    def quality_threshold(self, department: str, task_type: str = "") -> float:
        """Return threshold: use task_type override if available, else department default."""
        if task_type and task_type in _TASK_TYPE_THRESHOLDS:
            return _TASK_TYPE_THRESHOLDS[task_type]
        return self.get(department).quality_threshold

    def min_acceptable(self, department: str) -> float:
        return self.get(department).min_acceptable_score

    @staticmethod
    def task_type_threshold(task_type: str) -> float:
        """Get threshold for a specific task type, defaulting to 98.0."""
        return _TASK_TYPE_THRESHOLDS.get(task_type, 98.0)
