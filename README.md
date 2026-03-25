# AgentAI Agency — AI-Powered Agency Platform

Fully automated AI agency: UI task submission → AI worker pipeline → leader scoring (98% threshold) → email results.
Also includes a data collection email workflow: agency sends report requests → client replies with attachments → system uploads to account database.

## Setup

```bash
pip install -r requirements.txt
```

## Run tests

```bash
PYTHONPATH=.:src pytest tests/ -v
```

---

## CLI

```bash
# Create a handoff from Sales to Account
python src/cli.py initiate --from sales --to account \
  --inputs lead_profile deal_status target_kpi

# Approve / block by ID
python src/cli.py approve --id <uuid>
python src/cli.py block  --id <uuid> --reason "Client unresponsive"

# Dashboard
python src/cli.py status

# List all, or filter by state
python src/cli.py list
python src/cli.py list --state draft

# Scan for overdue handoffs (past SLA)
python src/cli.py refresh-overdue
```

Handoff state is persisted to `agency_state.json` in the working directory.

---

## REST API

```bash
PYTHONPATH=.:src uvicorn api:app --app-dir src --reload
```

Interactive docs: http://localhost:8000/docs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/handoffs` | Create a new handoff |
| `GET` | `/handoffs` | List all handoffs (`?state=draft`) |
| `GET` | `/handoffs/{id}` | Get a single handoff |
| `PATCH` | `/handoffs/{id}/approve` | Approve |
| `PATCH` | `/handoffs/{id}/block` | Block (`{"reason": "..."}`) |
| `POST` | `/handoffs/refresh-overdue` | Scan and flag overdue |
| `GET` | `/status` | Counts by state |
| `GET` | `/routes` | All available department routes |

### Task API (AI pipeline)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/tasks` | Create a new AI task |
| `GET` | `/tasks` | List tasks (`?status=` `?account_id=` `?campaign_id=`) |
| `GET` | `/tasks/{id}` | Get a single task |
| `POST` | `/tasks/{id}/run` | Execute task through LangGraph AI pipeline |
| `GET` | `/tasks/{id}/review-history` | Scoring audit trail |
| `POST` | `/tasks/{id}/cancel` | Cancel a task |

### Data Collection API (email workflow)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/data-collection/request` | Send data-report request email to client |
| `POST` | `/data-collection/inbound` | Webhook: process inbound email + attachments |

### Examples

```bash
# Create and run an AI task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"goal":"Create Q1 social media campaign","account_id":"acct-001","task_type":"creative"}'

curl -X POST http://localhost:8000/tasks/<uuid>/run

# Send data request email to client
curl -X POST http://localhost:8000/data-collection/request \
  -H "Content-Type: application/json" \
  -d '{"account_id":"acct-001","account_email":"client@brand.com","report_date":"2026-03"}'
```

---

## AI Pipeline Flow

```
POST /tasks/{id}/run
  → task_planner  (build step plan)
  → router        (pick department)
  → research      (web search + data)
  → specialist    (department AI worker)
  → leader_review (score ≥ 98% → pass, else retry up to 3×)
  → task_progress (next step or done)
  → email_notification (send result to stakeholder)
```

---

## Handoff states

```
DRAFT → APPROVED
DRAFT → BLOCKED
DRAFT → OVERDUE (auto, via refresh-overdue)
OVERDUE → APPROVED
OVERDUE → BLOCKED
```

---

## Project structure

```
src/
  models.py           — HandoffPolicy, HandoffInstance, HandoffState, Client, Project
  engine.py           — WorkflowEngine (handoff state machine, thread-safe)
  store.py            — Atomic JSON file persistence
  task_runner.py      — Bridge: FastAPI → LangGraph → DB
  api.py              — FastAPI REST API (handoffs + tasks + data-collection)
  cli.py              — Handoff CLI
  agents/             — LangGraph nodes (planner, router, research, specialists, leader)
  scoring/            — ScoreEngine + rubric registry (98% threshold, 11 depts)
  tasks/              — Task model, DAG, SLA tracker, KPI store
  db/                 — SQLite WAL-mode connection + repositories
  ingestion/          — email_ingestion.py + data_collection.py
  tools/              — EmailClient, FileStorage, WebSearch, DataAnalysis
  memory/             — Account + campaign memory retrieval
  context/            — Market trends + weather context
  ceo/                — CEO brain + health monitoring
  config/settings.py  — All env-driven settings (SCORE_THRESHOLD=98.0)
  policies/           — 33 inter-department route definitions + validator
tests/
  test_engine.py
  test_store.py
  test_validator.py
```
