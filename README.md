# Agency Workflow Engine (MVP)

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run validation
```bash
PYTHONPATH=. python src/main.py
python -m unittest discover -s tests -p 'test_*.py'
```

## Workflow CLI usage
```bash
PYTHONPATH=. python src/cli.py routes
PYTHONPATH=. python src/cli.py initiate sales account --payload '{"lead_profile":"A","deal_status":"won","target_kpi":"ROAS"}'
PYTHONPATH=. python src/cli.py list
PYTHONPATH=. python src/cli.py status
```

## Autonomous AI layer (all departments)
```bash
PYTHONPATH=. python src/cli.py ai-create-task creative "Generate 5 ad concepts" "CTR>2%" "2026-03-30" --context '{"brief":"new menu launch","brand":"Bakudan"}'
PYTHONPATH=. python src/cli.py ai-status
PYTHONPATH=. python src/cli.py ai-run-task <task_id>
```

Task model:
- goal
- KPI
- deadline
- score
- status

Scoring rule:
- score >= 98 => completed
- score < 98 => review/retry loop until fail threshold

## Run API
```bash
uvicorn src.api:app --reload --port 8000
```

## API quick examples
```bash
curl -X POST http://127.0.0.1:8000/handoffs \
  -H 'Content-Type: application/json' \
  -d '{"from_department":"sales","to_department":"account","payload":{"lead_profile":"A","deal_status":"won","target_kpi":"ROAS"}}'

curl -X POST http://127.0.0.1:8000/ai/tasks \
  -H 'Content-Type: application/json' \
  -d '{"department":"strategy","goal":"Create plan","kpi":"ROAS>3","deadline":"2026-03-30","context":{"market":"restaurant"}}'

curl -X POST http://127.0.0.1:8000/ai/tasks/<task_id>/run
curl http://127.0.0.1:8000/ai/status
```

## Email ingestion building block
- `src/ingestion/email_ingestion.py` provides:
  - email metadata parsing,
  - sender-to-account mapping,
  - attachment filename extraction.
