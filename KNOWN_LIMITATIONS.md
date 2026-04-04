# Master Control Center V1.1 — Known Limitations

---

## 1. Credentials Required for Live Operations

The following connectors return `OFFLINE` or errors without real credentials:

| Connector | Required Credentials | Impact Without |
|---|---|---|
| Marketing | `MARKETING_API_TOKEN` in `.env` | `check_health()` → 401; `upload` → fails |
| TaskFlow | `TASKFLOW_USERNAME` + `TASKFLOW_PASSWORD` | `check_health()` → 401; all actions fail |
| Growth Dashboard | `GROWTH_API_KEY` + correct URL | `check_health()` → connection error |

**Mitigation:** Set credentials in `.env` before going live.

---

## 2. Review Management MCP — Mock Connector

`review_connector.py` currently returns simulated responses. The actual MCP server
has not been integrated. Actions return `OFFLINE`/`WARNING` until MCP is wired.

---

## 3. Integration Full — No External Auth

`integration_connector.py` checks local script paths but does not authenticate
with any external service. Real integration with ToastPOS / QuickBooks requires
additional connector implementation.

---

## 4. SQLite Single-Writer

`JobDB` uses SQLite with default journal mode. Under high concurrency (>50
simultaneous writers), SQLite may return `database is locked` errors.

**Mitigation for V1.1:** Keep job throughput below 50/minute.
**V1.2:** Replace with PostgreSQL for production.

---

## 5. In-Memory Session Cache (TaskFlow)

TaskFlow session cookies are cached in `TaskFlowConnector._logged_in`.
This cache is lost on server restart. The connector auto re-logs in on 401/403,
so this is transparent — but the first request after restart is slower.

---

## 6. No Real-Time WebSocket Updates

The dashboard polls `/jobs` every 5 seconds (active) or 20 seconds (idle).
There is no WebSocket or SSE channel for real-time push.

**Mitigation:** Polling interval is configurable in `dashboard/app.js`.
**V1.2:** Add `websockets` for instant push.

---

## 7. File Upload Size Limit

Files larger than 50 MB (configurable via `MAX_UPLOAD_SIZE_MB`) are rejected
with HTTP 413. Chunked upload is not yet implemented.

---

## 8. Job Retry Without Persistence of Retry State

When a job retries, the `next_retry_at` timestamp is stored in the DB, but the
background retry scheduler is not yet implemented. Retry jobs will not
automatically re-execute until the next `POST /jobs/{id}/run` call or server
restart triggers a scan.

**Workaround:** Re-submit failed jobs manually via API or dashboard.

---

## 9. Audit Log Retention

Logs are stored indefinitely in SQLite. No log rotation or TTL is enforced.
High-volume environments may see database bloat.

**Workaround:** Periodically purge old logs via:
```sql
DELETE FROM job_logs WHERE created_at < datetime('now', '-30 days');
```

---

## 10. No Rate Limiting

The API does not enforce per-client rate limits. Misconfigured clients could
flood the job queue.

**V1.2:** Add FastAPI middleware for rate limiting.

---

## 11. No TLS on Local Dev Server

The default `uvicorn` startup does not use HTTPS. Credentials transmitted over
HTTP in local dev are visible on the network.

**Production:** Run behind a TLS-terminating proxy (nginx, Cloudflare) or use
`uvicorn --ssl-certfile` with a real certificate.
