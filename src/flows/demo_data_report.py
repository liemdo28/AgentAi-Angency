"""
FIRST MONEY FLOW — Email → Data Ingestion → AI Analysis → Score → Client Report

This is the complete, demo-ready flow that proves the AI agency works end-to-end.
Run this script to execute the entire pipeline with sample data (no LLM required).

Usage:
    PYTHONPATH=. python src/flows/demo_data_report.py

What it does:
    1. Simulates receiving a client email with a CSV performance report
    2. Parses the CSV and extracts KPIs automatically
    3. Creates a Data AI task in the database
    4. Runs the Data Specialist to produce a full performance report
    5. Scores the output against the Data department rubric
    6. Shows the complete result: score, report, and recommendations

This flow is the FIRST sellable product:
    - Agency charges client $500-2000/month for automated reporting
    - Client sends their data (email/upload)
    - AI processes, analyses, and produces a professional report
    - Human reviews and sends to client (or auto-sends if score >= 98)
"""
from __future__ import annotations

import csv
import io
import logging
import os
import sys
import tempfile
from pathlib import Path

# Ensure imports work from project root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("demo_data_report")


# ── Sample Client Data ────────────────────────────────────────────────────────

SAMPLE_CSV_DATA = """Campaign,Channel,Impressions,Clicks,CTR,CPC,Conversions,CPA,Spend,Revenue,ROAS
Spring Sale - FB Feed,Meta Feed,520000,12480,2.4%,3100,780,48000,38688000,156000000,4.03
Spring Sale - FB Reels,Meta Reels,185000,5920,3.2%,2800,420,37500,16576000,84000000,5.07
Brand Awareness - YT,YouTube Pre-roll,410000,3690,0.9%,5200,120,160000,19188000,24000000,1.25
Search - Generic,Google Search,95000,7600,8.0%,4500,950,36000,34200000,190000000,5.56
Search - Brand,Google Search,45000,9000,20.0%,1200,2100,5143,10800000,210000000,19.44
Retarget - Display,Display Network,320000,960,0.3%,8500,35,233143,8160000,7000000,0.86
CRM Email - Winback,Email,50000,7500,15.0%,0,380,0,0,38000000,0
"""


def run_demo():
    """Execute the complete demo flow."""

    print("\n" + "=" * 70)
    print("  AI AGENCY — DATA REPORT FLOW (Demo)")
    print("=" * 70)

    # ── Step 1: Parse Client CSV ──────────────────────────────────────
    print("\n[STEP 1] Parsing client performance data...")
    from src.ingestion.file_parser import extract_kpis_from_rows, parse_csv

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(SAMPLE_CSV_DATA)
        csv_path = f.name

    try:
        result = parse_csv(csv_path)
        print(f"  Parsed: {result.row_count} rows, {len(result.metadata.get('columns', []))} columns")
        print(f"  Columns: {result.metadata.get('columns', [])}")

        # ── Step 2: Extract KPIs ──────────────────────────────────────
        print("\n[STEP 2] Extracting KPIs from parsed data...")
        kpis = extract_kpis_from_rows(result.rows)
        print("  Extracted KPIs:")
        for k, v in kpis.items():
            if isinstance(v, float) and v > 1000:
                print(f"    {k}: {v:,.0f}")
            else:
                print(f"    {k}: {v}")

        # ── Step 3: Run Data Specialist ───────────────────────────────
        print("\n[STEP 3] Running Data Specialist AI agent...")
        from src.agents.specialists.data import DataSpecialist

        specialist = DataSpecialist()
        state = {
            "task_description": "Analyse Spring 2026 campaign performance and produce a client-ready report",
            "campaign_id": "camp-spring-2026",
            "account_id": "acct-nike-vn",
            "policy": {
                "from_department": "media",
                "to_department": "data",
                "required_inputs": ["campaign_data", "kpi_targets"],
                "expected_outputs": ["performance_report", "optimisation_recommendations"],
                "sla_hours": 24,
                "approver_role": "Data Lead",
            },
            "current_step": {
                "name": "Performance Diagnosis",
                "objective": "Analyse Spring campaign data and produce actionable insights",
            },
            "artifacts": kpis,
            "quality_threshold": 98.0,
        }

        gen_result = specialist.generate(state)
        output = gen_result["specialist_output"]
        print(f"  Generated report: {len(output)} characters, {len(output.splitlines())} lines")

        # ── Step 4: Score Output ──────────────────────────────────────
        print("\n[STEP 4] Scoring output against Data department rubric...")
        from src.scoring.score_engine import ScoreEngine

        engine = ScoreEngine()
        score_result = engine.score("data", output, task_type="data_report")

        overall = score_result["overall_score"]
        method = score_result["scoring_method"]
        breakdown = score_result["breakdown"]

        print(f"  Scoring method: {method}")
        print(f"  Overall score: {overall:.1f}/100")
        print(f"  Breakdown:")
        for criterion, score in breakdown.items():
            print(f"    {criterion}: {score:.1f}")

        # ── Step 5: Decision ──────────────────────────────────────────
        print("\n[STEP 5] Quality gate decision...")
        threshold = 98.0
        if overall >= threshold:
            print(f"  PASS — Score {overall:.1f} >= {threshold}")
            print("  -> Report can be auto-sent to client")
        else:
            print(f"  NEEDS REVIEW — Score {overall:.1f} < {threshold}")
            print("  -> Report queued for human review before sending")

        # ── Step 6: Show Report Preview ───────────────────────────────
        print("\n[STEP 6] Report preview (first 60 lines):")
        print("-" * 70)
        for line in output.splitlines()[:60]:
            print(f"  {line}")
        if len(output.splitlines()) > 60:
            print(f"  ... ({len(output.splitlines()) - 60} more lines)")
        print("-" * 70)

        # ── Summary ──────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("  DEMO COMPLETE")
        print("=" * 70)
        print(f"""
  Flow: Email CSV -> Parse -> KPI Extract -> Data AI -> Score -> Report

  Results:
    - Input: {result.row_count} campaign rows across {len(set(r.get('channel', '') for r in result.rows))} channels
    - KPIs extracted: {len(kpis)} metrics
    - Report: {len(output)} chars, {len(output.splitlines())} lines
    - Score: {overall:.1f}/100 ({method})
    - Decision: {'AUTO-SEND' if overall >= threshold else 'HUMAN REVIEW'}

  Business Value:
    - This flow replaces 4-8 hours of analyst work
    - Charge: $500-2000/month per client for automated reporting
    - Scale: Handle 50+ clients with 1 human reviewer
    - Upsell: Add optimisation execution for $2000-5000/month

  Next Steps:
    1. Connect real email inbox (IMAP) or file upload endpoint
    2. Add client branding to report template
    3. Set up auto-send for scores >= 98
    4. Build client dashboard to view reports
""")

        return {
            "kpis": kpis,
            "report_length": len(output),
            "score": overall,
            "method": method,
            "breakdown": breakdown,
        }

    finally:
        os.unlink(csv_path)


if __name__ == "__main__":
    run_demo()
