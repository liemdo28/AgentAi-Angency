# AgentAI Agency — Workflow Engine

Runtime system for managing inter-department handoffs in a marketing/creative agency.

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

### Example

```bash
curl -X POST http://localhost:8000/handoffs \
  -H "Content-Type: application/json" \
  -d '{"from_department":"sales","to_department":"account","inputs":["lead_profile","deal_status","target_kpi"]}'
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
  models.py       — HandoffPolicy, HandoffInstance, HandoffState
  engine.py       — WorkflowEngine (core business logic)
  store.py        — JSON file persistence
  policies/       — 33 inter-department route definitions
  cli.py          — Command-line interface
  api.py          — FastAPI REST API
tests/
  test_engine.py
  test_validator.py
```
