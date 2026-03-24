# Agency Workflow Engine (MVP → SaaS foundation)

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
# create client/project
PYTHONPATH=. python src/cli.py create-client "Bakudan" "Restaurant"
PYTHONPATH=. python src/cli.py create-project <client_id> "Growth Sprint" "Scale revenue" "AM"

# run handoff flow
PYTHONPATH=. python src/cli.py initiate sales account --payload '{"lead_profile":"A","deal_status":"won","target_kpi":"ROAS"}' --client-id <client_id> --project-id <project_id>
PYTHONPATH=. python src/cli.py status
PYTHONPATH=. python src/cli.py list --project-id <project_id>
```

## Run API
```bash
export AGENCY_API_KEY=local-dev-key
uvicorn src.api:app --reload --port 8000
```

## API quick examples
```bash
curl -X POST http://127.0.0.1:8000/clients \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: local-dev-key' \
  -d '{"name":"Bakudan","industry":"Restaurant"}'

curl -X POST http://127.0.0.1:8000/projects \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: local-dev-key' \
  -d '{"client_id":"<client_id>","name":"Growth Sprint","objective":"Scale revenue","owner":"AM"}'

curl -X POST http://127.0.0.1:8000/handoffs \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: local-dev-key' \
  -d '{"from_department":"sales","to_department":"account","payload":{"lead_profile":"A","deal_status":"won","target_kpi":"ROAS"},"client_id":"<client_id>","project_id":"<project_id>"}'

curl -H 'x-api-key: local-dev-key' http://127.0.0.1:8000/status
curl -H 'x-api-key: local-dev-key' http://127.0.0.1:8000/routes
```
