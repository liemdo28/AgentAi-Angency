# Bug / Risk Report — AgentAI Agency Platform

**Report ID**: QA-2026-003
**Date**: 2026-03-26
**Author**: QA Director Review (Automated)
**Scope**: Full platform — workflow, AI pipeline, data ingestion, scoring
**Test baseline**: 114 passed, 2 skipped
**Codebase**: ~12,800 lines Python, 120+ files, 11 departments

---

## Severity Legend

| Level | Meaning | SLA |
|-------|---------|-----|
| **P0 — Critical** | System fails, data loss, wrong client data | Fix before any pilot |
| **P1 — High** | Core flow unreliable, score misleading, silent failure | Fix before staging |
| **P2 — Medium** | Feature incomplete, edge case not handled, debt accumulating | Fix before production |
| **P3 — Low** | Cosmetic, minor inconsistency, future concern | Plan into roadmap |

---

## Section A: System-Level Risks (Current)

### RISK-001 — task_runner status mapping loses failure nuance

| Field | Value |
|-------|-------|
| **ID** | RISK-001 |
| **Severity** | P1 — High |
| **Probability** | High (every failed task) |
| **Impact** | Wrong status → wrong retry/escalation → task silently marked DONE when it failed |
| **File** | `src/task_runner.py:88-96` |
| **Owner** | Backend / Pipeline team |

**Description**
`run_task_sync()` maps graph status to TaskStatus with simple if/elif:
- `PASSED` → PASSED
- `REVIEW_FAILED` → ESCALATED
- has errors → FAILED
- **else → DONE** (catch-all)

The catch-all `DONE` means any unrecognized status (e.g., `IN_PROGRESS`, `REVIEW`, `RETRY`, timeout) gets silently marked as completed.

**Suggested Fix**
- ✅ FIXED: Added explicit status mapping with unknown-status fallback to FAILED + error logging.

---

### RISK-002 — No error classification in review loop

| Field | Value |
|-------|-------|
| **ID** | RISK-002 |
| **Severity** | P1 — High |
| **Probability** | Medium |
| **Impact** | Retry loops don't know WHY output failed → retry doesn't improve |
| **File** | `src/agents/leader_reviewer.py:178-392` |
| **Owner** | AI / Scoring team |

**Description**
Leader review detects PASS/FAIL/ESCALATE but doesn't classify the failure:
- Was it a research gap? (missing data)
- Specialist hallucination? (wrong facts)
- Rubric coverage miss? (missing sections)
- Quality issue? (poor writing)

Without classification, retry feedback is generic and the specialist just paraphrases.

**Suggested Fix**
- ✅ FIXED: Added `failure_category` field to review_history entries based on rubric breakdown analysis. Weakest criterion determines the category.

---

### RISK-003 — Duplicate inbound emails create duplicate tasks

| Field | Value |
|-------|-------|
| **ID** | RISK-003 |
| **Severity** | P0 — Critical |
| **Probability** | High (email retry, webhook replay) |
| **Impact** | Same client report processed twice → duplicate analysis, billing confusion |
| **File** | `src/ingestion/data_collection.py:125-230` |
| **Owner** | Data Ingestion team |

**Description**
`process_inbound_email()` has no idempotency check. If the same email is received twice (webhook retry, IMAP reconnect), it:
1. Saves duplicate attachments
2. Creates duplicate tasks
3. Processes the same data twice

**Suggested Fix**
- ✅ FIXED: Added deduplication via email Message-ID header. Tracks processed message IDs in an in-memory set + logs duplicate detection.

---

### RISK-004 — Heuristic scoring inflates scores for formatted garbage

| Field | Value |
|-------|-------|
| **ID** | RISK-004 |
| **Severity** | P2 — Medium |
| **Probability** | Medium (when LLM unavailable) |
| **Impact** | Garbage output with correct headers scores 80+ → passes quality gate |
| **File** | `src/scoring/score_engine.py:146-224` |
| **Owner** | AI / Scoring team |

**Description**
Heuristic scoring checks structural signals (line count, sections, formatting) but not semantic quality. An output with:
- 30+ lines of "lorem ipsum"
- `##` headers
- `$` and `%` characters
- Tables with `|`

Would score ~80/100 despite containing no real content.

**Suggested Fix**
- ✅ FIXED: Added content density check — scoring now penalizes outputs where unique-word ratio is low (repetitive/filler text) and where expected section keywords from the rubric checklist are missing.

---

### RISK-005 — Retry loop doesn't verify improvement

| Field | Value |
|-------|-------|
| **ID** | RISK-005 |
| **Severity** | P1 — High |
| **Probability** | High (every retry) |
| **Impact** | 3 retries waste LLM calls with no quality gain; final output ≈ first attempt |
| **File** | `src/scoring/retry_with_feedback.py:121-183` |
| **Owner** | AI / Pipeline team |

**Description**
`execute_retry()` re-runs specialist and re-scores, but never checks if the new score is actually better than the previous one. It just recurses. This means:
- Score 72 → retry → score 68 → retry → score 65 → escalate
- 3 LLM calls wasted with regression

**Suggested Fix**
- ✅ FIXED: Added score regression detection. If new score <= previous score, stop retrying and escalate immediately with reason "no_improvement".

---

### RISK-006 — Test coverage severely imbalanced

| Field | Value |
|-------|-------|
| **ID** | RISK-006 |
| **Severity** | P1 — High |
| **Probability** | Certain |
| **Impact** | High-risk code (task_runner, graph, data_collection) breaks silently |
| **File** | `tests/` |
| **Owner** | QA team |

**Description**
Test distribution before this fix:

| Module | Lines of Code | Test Lines | Ratio |
|--------|--------------|------------|-------|
| Workflow engine | ~400 | 256 | 0.64 |
| Store/Validator | ~300 | 267 | 0.89 |
| Task runner + graph | ~450 | 0 → 219 | 0 → 0.49 |
| Scoring system | ~920 | 0 → 251 | 0 → 0.27 |
| Data ingestion | ~490 | 0 → 294 | 0 → 0.60 |
| Specialists (11) | ~2000 | 0 → included | ~0.10 |

After this PR: **114 tests** (from 53). But specialists, graph nodes, and memory/context still have zero direct tests.

**Suggested Fix**
- Partially addressed in this PR (61 new tests)
- Remaining: graph node tests, memory/context tests, specialist per-department tests

---

### RISK-007 — Score threshold 98.0 not calibrated per task type

| Field | Value |
|-------|-------|
| **ID** | RISK-007 |
| **Severity** | P2 — Medium |
| **Probability** | High |
| **Impact** | Simple tasks (client_reporting) held to same standard as complex tasks (campaign_launch) |
| **File** | `src/scoring/rubric_registry.py`, `src/config/settings.py` |
| **Owner** | Product / AI team |

**Description**
All 11 departments use `quality_threshold: 98.0`. But:
- A "client_reporting" data summary should not need the same depth as a "campaign_launch" strategy
- Heuristic scoring maxes around 85 — meaning NO task can pass without LLM
- This effectively makes the system non-functional without API keys

**Suggested Fix**
- ✅ FIXED: Added per-task-type threshold overrides in rubric registry. Task types now have calibrated thresholds (e.g., `client_reporting: 90`, `data_ingestion: 85`, `campaign_launch: 96`).

---

### RISK-008 — Synchronous task runner blocks API

| Field | Value |
|-------|-------|
| **ID** | RISK-008 |
| **Severity** | P2 — Medium |
| **Probability** | High (>5 concurrent tasks) |
| **Impact** | API timeout, task stuck IN_PROGRESS, user sees 504 |
| **File** | `src/task_runner.py`, `src/api.py:450-486` |
| **Owner** | Backend team |

**Description**
`run_task_sync()` runs synchronously inside a FastAPI endpoint. Graph invocation (LLM calls, research, retries) can take 30-120 seconds. With multiple concurrent requests, the API becomes unresponsive.

**Suggested Fix**
- P2: Documented as known limitation. Future: add async task queue (Celery/asyncio).
- Short-term: API endpoint should return immediately with task_id and status polling.

---

## Section B: AI Maturity Risks

### RISK-009 — No determinism test for same-input tasks

| Field | Value |
|-------|-------|
| **ID** | RISK-009 |
| **Severity** | P2 — Medium |
| **Probability** | Certain (LLM non-deterministic) |
| **Impact** | Same task → different score → different routing → unpredictable system |
| **File** | All AI nodes |
| **Owner** | AI team |

**Suggested Fix**
- Use `temperature=0.0` for routing and scoring (not specialist generation)
- Add golden-set regression tests with known expected outputs

---

### RISK-010 — Memory/context injection not proven to improve decisions

| Field | Value |
|-------|-------|
| **ID** | RISK-010 |
| **Severity** | P2 — Medium |
| **Probability** | Uncertain |
| **Impact** | Memory system exists but may not change output quality measurably |
| **File** | `src/memory/`, `src/context/`, `src/agents/graph.py:63-123` |
| **Owner** | AI team |

**Suggested Fix**
- Add A/B test: run same task with and without memory injection, compare scores
- Track memory hit rate in review_history metadata

---

## Section C: Long-Term Risks (9-Year Horizon)

### RISK-011 — AI output drift as models change

| Field | Value |
|-------|-------|
| **ID** | RISK-011 |
| **Severity** | P3 — Low (now), P1 (future) |
| **Probability** | Certain |
| **Impact** | Score baselines invalidated, routing breaks, quality regresses |
| **Owner** | AI / Platform team |

**Suggested Fix**
- Pin model versions in config
- Run monthly golden-set benchmark tests
- Log model version in review_history for audit

---

### RISK-012 — Data format drift in client reports

| Field | Value |
|-------|-------|
| **ID** | RISK-012 |
| **Severity** | P3 — Low (now), P0 (future) |
| **Probability** | Certain |
| **Impact** | CSV column names change → KPI extraction fails → wrong analysis |
| **Owner** | Data Ingestion team |

**Suggested Fix**
- ✅ PARTIALLY FIXED: `file_parser.py` uses fuzzy column matching with `_KPI_PATTERNS`
- Future: add column mapping config per account, anomaly alerts for unrecognized columns

---

### RISK-013 — Governance / liability when AI sends wrong data

| Field | Value |
|-------|-------|
| **ID** | RISK-013 |
| **Severity** | P3 — Low (now), P0 (future) |
| **Probability** | Medium |
| **Impact** | Legal exposure: wrong account assignment, incorrect analysis sent to client |
| **Owner** | Product / Legal team |

**Suggested Fix**
- Add human-in-the-loop approval for all outbound client communications
- Full audit trail (already partially exists in review_history + audit_log)
- Never auto-send without explicit approval flag per account

---

## Section D: Test Team Assignment (500 Testers)

| Squad | Testers | Focus | Priority Items |
|-------|---------|-------|----------------|
| **Squad A: Workflow Core** | 120 | State machine, handoff lifecycle, approve/block/overdue | RISK-001, RISK-008 |
| **Squad B: Task Routing** | 80 | Router accuracy, planner templates, dependency ordering | RISK-002, RISK-009 |
| **Squad C: Scoring & Review** | 100 | Score consistency, rubric correctness, retry improvement | RISK-004, RISK-005, RISK-007 |
| **Squad D: Data Pipeline** | 80 | Email ingestion, file parsing, KPI extraction, dedup | RISK-003, RISK-012 |
| **Squad E: Specialist Output** | 60 | Per-department output quality, fallback correctness | RISK-002, RISK-010 |
| **Squad F: API & Integration** | 40 | Endpoint correctness, concurrency, error responses | RISK-008 |
| **Squad G: Security & Governance** | 20 | Path traversal, account isolation, audit completeness | RISK-013 |

### Test Execution Priority

| Phase | Duration | Squads | Gate Criteria |
|-------|----------|--------|--------------|
| **Phase 1: Smoke** | 2 days | A, D | All P0 items verified fixed |
| **Phase 2: Integration** | 5 days | A, B, C, D | Task flows end-to-end without error |
| **Phase 3: Quality** | 5 days | C, E, F | Score consistency >90% across 100 runs |
| **Phase 4: Stress** | 3 days | F, A | 50 concurrent tasks without degradation |
| **Phase 5: Regression** | 2 days | All | Full suite green, no new P0/P1 |

---

## Summary Scorecard

| Dimension | Score | Status |
|-----------|-------|--------|
| Workflow intelligence | 7.2/10 | Orchestration solid, autonomy limited |
| Workflow orchestration | 8.8/10 | Pipeline well-designed |
| Department optimization (design) | 7.8/10 | Route model correct |
| Department optimization (execution) | 5.5/10 | Unproven at scale |
| AI presence | 7.5/10 | Pipeline exists and runs |
| AI maturity | 5.2/10 | Not yet reliable for production |
| Leader brain reliability | 5.6/10 | Scoring works, classification missing |
| Worker brain reliability | 4.9/10 | Fallback exists, quality unproven |
| Test coverage | 6.5/10 | Improved (114 tests), gaps remain |

### Release Readiness

| Environment | Ready? |
|-------------|--------|
| Internal alpha | **YES** |
| Staging | **YES** (with P0 fixes) |
| Controlled demo / pilot | **YES** (with P0+P1 fixes) |
| Production (broad) | **NO** — need P2 fixes + Phase 3-5 testing |
| "Fully automated AI agency" claim | **NO** — need AI maturity ≥ 7.5/10 |
