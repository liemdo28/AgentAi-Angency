# Master Control Center V1.1 — Rollback & Recovery

---

## Emergency Rollback

### If the Unified API starts failing catastrophically:

**Step 1: Stop the server**
```bash
# Find the uvicorn process
taskkill /F /FI "WINDOWTITLE eq *uvicorn*"
# Or kill by port
FOR /F "tokens=5" %P IN ('netstat -ano ^| findstr :8001') DO taskkill /F /PID %P
```

**Step 2: Restore previous state**

If you have a Git backup:
```bash
git checkout HEAD -- src/unified/
```

**Step 3: Restart**
```bash
python -m uvicorn src.unified.api:app --host 0.0.0.0 --port 8001
```

---

## Database Recovery

### If `data/unified.db` is corrupted:

1. Stop the server.
2. Backup (do not skip):
   ```bash
   copy data\unified.db data\unified.db.broken
   ```
3. Delete the database:
   ```bash
   del data\unified.db
   ```
4. Restart server — tables are auto-created on startup.
5. Jobs are gone; resubmit any lost jobs.

### Reset all jobs (fresh start):
```bash
del data\unified.db
python -c "from src.unified.jobs import JobDB; print('DB reset:', JobDB())"
```

### View job history before reset:
```bash
python -c "
from src.unified.jobs import JobDB
db = JobDB()
jobs = db.list_jobs(limit=100)
for j in jobs:
    print(j.id, j.status, j.project_id, j.action_id)
"
```

---

## Clearing Stale Cache

### If `__pycache__` causes stale code errors:

```bash
# Windows
for /d /r src %d in (__pycache__) do @if exist "%d" rd /s /q "%d"

# Or via Python
python -c "import shutil, glob; [shutil.rmtree(p) for p in glob.glob('src/**/__pycache__', recursive=True)]"
```

---

## Fixing Common Startup Errors

### `ModuleNotFoundError: No module named 'src'`

```bash
cd E:\Project\Master\agentai-agency
set PYTHONPATH=E:\Project\Master\agentai-agency\src
# Or add to system environment variables
```

### `sqlite3.OperationalError: database is locked`

Too many concurrent writers. Kill stale connections:
```python
from src.unified.jobs import JobDB
db = JobDB.get_instance()
# Force close and reopen
db._db.close()
# Restart server
```

### `datetime.utcnow() takes no arguments`

Run the datetime fix script:
```bash
python -c "
import glob, re
for path in glob.glob('src/**/*.py', recursive=True):
    with open(path, 'r', encoding='utf-8') as f:
        c = f.read()
    if 'utcnow' in c:
        c = c.replace('datetime.utcnow()', 'datetime.now(timezone.utc)')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(c)
        print('Fixed:', path)
"
```

---

## If a Job Gets Stuck

### Force-fail a stuck job:
```python
from src.unified.jobs import JobDB, JobStatus
db = JobDB.get_instance()
job = db.get_job("job_xxx")
if job:
    job.status = JobStatus.FAILED
    job.error_message = "Manually cancelled by admin"
    job.finished_at = datetime.now(timezone.utc)
    db.update_job(job)
    print("Job forced to FAILED")
```

### Manually trigger a retry:
```bash
curl -X POST http://localhost:8001/jobs/{job_id}/run
```

---

## Pre-Deployment Safety Checklist

Before deploying V1.1 to production:

- [ ] `.env` exists and all required credentials are set
- [ ] `data/unified.db` is writable by the server process
- [ ] `src/**/__pycache__` has been cleared
- [ ] `python uat_test.py` passes 26/26
- [ ] All connectors return 200 on health checks (or expected UNAUTHORIZED)
- [ ] Dashboard loads and job polling works
- [ ] File upload test passes
- [ ] `KNOWN_LIMITATIONS.md` has been reviewed and accepted by stakeholders
