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

## CLI usage
```bash
PYTHONPATH=. python src/cli.py routes
PYTHONPATH=. python src/cli.py initiate sales account --payload '{"lead_profile":"A","deal_status":"won","target_kpi":"ROAS"}'
PYTHONPATH=. python src/cli.py list
PYTHONPATH=. python src/cli.py status
```

## Run API
```bash
uvicorn src.api:app --reload --port 8000
```

## API quick examples
```bash
curl -X POST http://127.0.0.1:8000/handoffs \
  -H 'Content-Type: application/json' \
  -d '{"from_department":"sales","to_department":"account","payload":{"lead_profile":"A","deal_status":"won","target_kpi":"ROAS"}}'

curl http://127.0.0.1:8000/status
curl http://127.0.0.1:8000/routes
```
