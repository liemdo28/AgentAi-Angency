# Master Control Center V1.1 — Manual Test Checklist

> Perform these steps in order. Check each box when verified.
> Record actual values (response time, HTTP status, output) for audit.

---

## Phase 1: Prerequisites — Automated UAT ✅
**Run:** `python uat_test.py`

```
python uat_test.py
```
- [ ] All 26 tests pass
- [ ] No errors or failures in output

---

## Phase 2: Server Startup
**Start in terminal 1:**
```bash
python -m uvicorn src.unified.api:app --host 0.0.0.0 --port 8001 --reload
```

- [ ] Server starts without errors
- [ ] `http://localhost:8001/docs` is accessible (Swagger UI)
- [ ] `GET /health` returns 200

---

## Phase 3: Connector Health Checks

Run each command and record status/latency:

### Marketing
```bash
curl -s http://localhost:8001/projects/marketing/health | jq .
```
- [ ] Status is `online` OR `unauthorized` (if no token)
- [ ] Latency < 5s

### Marketing + Growth (via unified connector)
```bash
curl -s http://localhost:8001/projects/marketing/health | jq .
```
- [ ] Returns 200 (status may be `unauthorized` if no MARKETING_API_TOKEN)
- [ ] Branch-state endpoint reachable (GROWTH_BASE_URL)

### TaskFlow
```bash
curl -s http://localhost:8001/projects/dashboard-taskflow/health | jq .
```
- [ ] Status is `online` OR `unauthorized`

### Integration Full
```bash
curl -s http://localhost:8001/projects/integration-full/health | jq .
```
- [ ] Returns 200

### Review Management
```bash
curl -s http://localhost:8001/projects/review-management/health | jq .
```
- [ ] Returns 200

### AgentAI Agency
```bash
curl -s http://localhost:8001/projects/agentai-agency/health | jq .
```
- [ ] Returns 200

---

## Phase 4: Job Queue — Marketing Upload (requires real token)

### Create a marketing upload job
```bash
curl -s -X POST http://localhost:8001/jobs \
  -H "Content-Type: application/json" \
  -d '{"project_id":"marketing","action_id":"marketing.upload","payload":{"test":true},"requested_by":"manual_test"}' | jq .
```
- [ ] Returns 200
- [ ] Response has `job.id`
- [ ] Job status is `pending` then transitions to `running` → `success` OR `retrying`

### Check job status
```bash
curl -s http://localhost:8001/jobs/{job_id} | jq .
```
- [ ] Returns 200
- [ ] `status` field is present
- [ ] `logs` array contains entries

### Check job summary
```bash
curl -s http://localhost:8001/jobs/summary | jq .
```
- [ ] `total` count is correct
- [ ] `by_status` breakdown is correct

---

## Phase 5: File Upload Test

### Create a test file
```bash
echo "Test campaign data" > data/test_upload.csv
```

### Upload via dashboard (or curl)
```bash
curl -s -X POST http://localhost:8001/projects/marketing/actions/marketing.upload \
  -F "file=@data/test_upload.csv" \
  -F "requested_by=manual_test" | jq .
```
- [ ] Returns 200
- [ ] `success: true` OR connector returns expected response
- [ ] No 422 Unprocessable Entity error

### Invalid file type (e.g., .exe)
```bash
echo "bad" > data/test.exe
curl -s -X POST http://localhost:8001/projects/marketing/actions/marketing.upload \
  -F "file=@data/test.exe" \
  -F "requested_by=manual_test"
```
- [ ] Returns 422 with `File type not allowed` message

### Oversized file (>50MB)
```bash
# Create a 51MB file
dd if=/dev/zero of=data/test_large.bin bs=1M count=51
curl -s -X POST http://localhost:8001/projects/marketing/actions/marketing.upload \
  -F "file=@data/test_large.bin" \
  -F "requested_by=manual_test"
```
- [ ] Returns 413 or 422 with `exceeds maximum size` message

---

## Phase 6: Cancel Job

```bash
# Create a job
JOB=$(curl -s -X POST http://localhost:8001/jobs \
  -H "Content-Type: application/json" \
  -d '{"project_id":"marketing","action_id":"marketing.upload"}')
JOB_ID=$(echo $JOB | jq -r '.job.id')

# Cancel it
curl -s -X POST http://localhost:8001/jobs/${JOB_ID}/cancel | jq .
```
- [ ] Returns 200
- [ ] `job.status` is `cancelled`

---

## Phase 7: Retry & Error Handling

### Trigger a real connector failure (invalid action ID)
```bash
curl -s -X POST http://localhost:8001/jobs \
  -H "Content-Type: application/json" \
  -d '{"project_id":"marketing","action_id":"nonexistent_action","payload":{}}' | jq .
sleep 6
curl -s http://localhost:8001/jobs/{job_id} | jq '.job.status'
```
- [ ] Job goes `pending` → `running` → `retrying` → `failed`
- [ ] After 3 retries, job reaches `failed` state
- [ ] `error_message` is populated in job record

### Check audit logs
```bash
curl -s "http://localhost:8001/logs?limit=5" | jq .
```
- [ ] Logs show `job created`, `started`, `failed/retrying` entries
- [ ] Each log has `level`, `message`, `context`, `created_at`

---

## Phase 8: Dashboard UI (Action Center)

Start dashboard server:
```bash
cd dashboard && python -m http.server 8080
```

Open `http://localhost:8080` in browser:
- [ ] Page loads without JavaScript errors
- [ ] Jobs tab shows recent jobs with status badges
- [ ] Filters (All/Pending/Running/Success/Failed) work
- [ ] Clicking a job shows detail modal with log trail

---

## Phase 9: Stress Test — 10 Parallel Jobs

```bash
# Run via Python
python -c "
import concurrent.futures, httpx, json, sys

def create_job(i):
    r = httpx.post('http://localhost:8001/jobs', json={
        'project_id': 'marketing',
        'action_id': 'marketing.upload',
        'payload': {'seq': i},
    })
    return r.status_code, r.json().get('job', {}).get('id')

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(create_job, range(10)))

ok = sum(1 for s, _ in results if s == 200)
print(f'{ok}/10 jobs created successfully')
sys.exit(0 if ok == 10 else 1)
"
```
- [ ] All 10 return 200
- [ ] No server crash or 500 errors
- [ ] All 10 job IDs are unique

---

## Phase 10: Timeout Test

```bash
curl -s -X POST http://localhost:8001/jobs \
  -H "Content-Type: application/json" \
  -d '{"project_id":"marketing","action_id":"marketing.health","payload":{}}'
# Wait 60s (JOB_DEFAULT_TIMEOUT)
# Check: job reaches SUCCESS or FAILED (not stuck running)
```

---

## Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Developer | | | |
| QA | | | |
| DevOps | | | |
| Product Owner | | | |

**V1.1 Status:** ☐ PASS  ☐ PASS WITH NOTES  ☐ FAIL

Notes:
_
