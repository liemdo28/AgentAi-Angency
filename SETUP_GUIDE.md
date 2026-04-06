# Master Control Center V1.1 — Setup Guide

## Prerequisites

- Python 3.11+ (tested on 3.13)
- httpx, fastapi, uvicorn, pydantic (see `requirements.txt`)
- Network access to child project URLs

---

## Step 1: Copy and configure `.env`

```bash
cp .env.example .env
```

Edit `.env` and fill in the credentials below. **All are required.**

---

## Step 2: Credential Reference

### Marketing (`marketing.bakudanramen.com`)
```
MARKETING_BASE_URL=https://marketing.bakudanramen.com
MARKETING_API_TOKEN=<your_bearer_token>
MARKETING_TIMEOUT=120
```
- Generate a session token:
  `POST https://marketing.bakudanramen.com/api/auth/token`
- Exchange that session token for a long-lived API key:
  `POST https://marketing.bakudanramen.com/api/auth/key`
- Use the returned `gdr_...` value as `MARKETING_API_TOKEN`
- Token is sent as `Authorization: Bearer <token>` header

### TaskFlow (`dashboard.bakudanramen.com`)
```
TASKFLOW_BASE_URL=https://dashboard.bakudanramen.com
TASKFLOW_USERNAME=<your_email>
TASKFLOW_PASSWORD=<your_password>
TASKFLOW_TIMEOUT=60
```
- Use the same credentials you use in the browser
- Session cookie is cached in-memory; auto re-logs in on 401/403

### Growth Dashboard (`marketing.bakudanramen.com/api`)
```
GROWTH_BASE_URL=https://marketing.bakudanramen.com/api
GROWTH_API_KEY=<gdr_...>
GROWTH_TIMEOUT=60
```
- The same `gdr_...` key can be used for both `MARKETING_API_TOKEN` and `GROWTH_API_KEY`
- Branch-state.php and analytics.php are included in the `marketing` connector
- API is served from the DreamHost PHP backend behind `marketing.bakudanramen.com`

### Integration Full (Toast-QB sync)
```
INTEGRATION_TIMEOUT=300
```
- Runs local sync scripts; no external auth needed
- Timeout set to 5 minutes for long-running operations

### Review Management MCP
```
# No external credentials required for V1.1
# Connector returns simulated responses until MCP is wired up
```

### Agency API
```
AGENCY_BASE_URL=http://localhost:8000
AGENCY_TIMEOUT=10
```

---

## Step 3: Install dependencies

```bash
cd E:\Project\Master\agentai-agency
pip install -r requirements.txt
```

---

## Step 4: Initialize the database

```bash
python -c "from src.unified.jobs import JobDB; JobDB()"
```

This creates `data/unified.db` with the job queue tables.

---

## Step 5: Start the Unified API

```bash
python -m uvicorn src.unified.api:app --host 0.0.0.0 --port 8001 --reload
```

---

## Step 6: Start the Dashboard (optional, in a new terminal)

```bash
cd dashboard
# Serve index.html via any static server, e.g.:
python -m http.server 8080
```

Then open `http://localhost:8080` in your browser.

---

## Step 7: Run the UAT test suite

```bash
python uat_test.py
```

Expected output: `ALL TESTS PASSED`

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AttributeError: 'Field' object has no attribute 'copy'` | Delete `src/**/__pycache__`, restart server |
| `GET /projects` returns `{}` | Ensure `marketing_api_token` is set in `.env` |
| Job stuck in `retrying` | Check network + child project health |
| `datetime.utcnow()` errors | Ensure Python 3.12+; all files should use `datetime.now(timezone.utc)` |
| Upload fails 422 | Ensure file is sent as `multipart/form-data` with a `file` field |
| All connectors return `OFFLINE` | Verify URLs in `.env` are reachable from this machine |
