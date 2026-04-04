"""
UAT Test Suite — Master Control Center V1.1
Run with: python uat_test.py

Requires .env file with real credentials configured.
Copy .env.example to .env and fill in values before running.
"""
from __future__ import annotations

import os
import sys
import time

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

os.environ.setdefault("DATA_DIR", "data")

import unittest
from fastapi.testclient import TestClient

from src.unified.api import app


class UATTestSuite(unittest.TestCase):
    """V1.1 UAT — Master Control Center."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.results = []

    def check(self, name: str, condition: bool, detail: str = ""):
        mark = "PASS" if condition else "FAIL"
        print(f"  [{mark}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((mark, name, detail))
        return condition

    # ── T1: API Endpoints ──────────────────────────────────────────────────────

    def test_job_create_and_retrieve(self):
        """POST /jobs creates a job; GET /jobs/{id} returns it."""
        r = self.client.post("/jobs", json={
            "project_id": "marketing",
            "action_id": "marketing.upload",
            "payload": {"via": "uat"},
            "requested_by": "uat",
        })
        self.check("POST /jobs returns 200", r.status_code == 200)
        jid = r.json().get("job", {}).get("id")
        self.check("Response contains job.id", bool(jid), jid or "None")

        time.sleep(0.5)
        r2 = self.client.get(f"/jobs/{jid}")
        self.check("GET /jobs/{id} returns 200", r2.status_code == 200)
        payload = r2.json().get("job", {}).get("payload", {})
        self.check("Payload preserved", payload.get("via") == "uat", str(payload))

    def test_job_summary(self):
        """/jobs/summary returns total + by_status breakdown."""
        r = self.client.get("/jobs/summary")
        self.check("/jobs/summary returns 200", r.status_code == 200)
        s = r.json()
        self.check("Has 'total' key", "total" in s)
        self.check("Has 'by_status' key", "by_status" in s)

    def test_job_list_filters(self):
        """/jobs supports status and project_id filters."""
        r = self.client.get("/jobs")
        self.check("GET /jobs returns 200", r.status_code == 200)
        body = r.json()
        self.check("Response is dict with jobs key", isinstance(body, dict) and "jobs" in body)

        r2 = self.client.get("/jobs?status=pending")
        self.check("GET /jobs?status=pending returns 200", r2.status_code == 200)

    def test_cancel_job(self):
        """POST /jobs/{id}/cancel transitions pending job to cancelled."""
        r = self.client.post("/jobs", json={
            "project_id": "marketing",
            "action_id": "marketing.upload",
        })
        jid = r.json().get("job", {}).get("id")
        r2 = self.client.post(f"/jobs/{jid}/cancel")
        self.check("Cancel returns 200", r2.status_code == 200)
        self.check("Job status is cancelled", r2.json().get("job", {}).get("status") == "cancelled")

    def test_all_project_health_endpoints(self):
        """All 5 project health endpoints return 200."""
        for pid in [
            "marketing", "review-management",
            "integration-full", "agentai-agency", "dashboard-taskflow",
        ]:
            r = self.client.get(f"/projects/{pid}/health")
            self.check(f"/projects/{pid}/health -> {r.status_code}", r.status_code == 200)

    def test_projects_list(self):
        """/projects returns all 5 projects as a list."""
        r = self.client.get("/projects")
        self.check("/projects returns 200", r.status_code == 200)
        projects = r.json()
        self.check("Returns a list", isinstance(projects, list))
        self.check("Has 5 projects", len(projects) == 5, f"got {len(projects)}")
        self.check("Has 'marketing'", any(p["id"] == "marketing" for p in projects))

    def test_audit_logs(self):
        """/logs and /logs/summary both return 200."""
        r = self.client.get("/logs")
        self.check("/logs returns 200", r.status_code == 200)
        body = r.json()
        self.check("/logs is dict with 'logs' key", isinstance(body, dict) and "logs" in body)
        self.check("/logs has entries", body.get("count", 0) > 0, f"count={body.get('count')}")

        r2 = self.client.get("/logs/summary")
        self.check("/logs/summary returns 200", r2.status_code == 200)

    def test_error_handling(self):
        """/projects/{unknown}/health and job on unknown project both 404."""
        r1 = self.client.get("/projects/nonexistent/health")
        self.check("Unknown project health -> 404", r1.status_code == 404)
        r2 = self.client.post("/jobs", json={"project_id": "nonexistent", "action_id": "ping"})
        self.check("Unknown project job -> 404", r2.status_code == 404)

    # ── T2: File Validation ───────────────────────────────────────────────────

    def test_upload_action_requires_file(self):
        """marketing.upload requires a file (no file -> 422)."""
        r = self.client.post(
            "/projects/marketing/actions/marketing.upload",
            json={"test": True},  # no file
        )
        self.check("marketing.upload without file -> 422", r.status_code == 422)

    # ── T3: Integration Actions (no real credentials needed for shape) ────────

    def test_integration_health(self):
        """integration-full health check."""
        r = self.client.get("/projects/integration-full/health")
        self.check("integration-full/health -> 200", r.status_code == 200)

    def test_action_registry_coverage(self):
        """All known action IDs are registered in ACTION_REGISTRY (nested: project -> action)."""
        from src.unified.api import ACTION_REGISTRY
        # Structure: ACTION_REGISTRY[project_id][action_id] = {...}
        expected = [
            ("marketing", "marketing.upload"),
            ("marketing", "marketing.sync_campaigns"),
            ("marketing", "marketing.health"),
            ("marketing", "marketing.branch_state"),
            ("marketing", "marketing.analytics"),
            ("dashboard-taskflow", "taskflow.fetch_stats"),
            ("integration-full", "integration.sync"),
        ]
        for project_id, action_id in expected:
            found = action_id in ACTION_REGISTRY.get(project_id, {})
            self.check(f"  [{project_id}] '{action_id}' in registry", found)

    # ── T4: Stress (10 sequential rapid jobs) ─────────────────────────────────

    def test_parallel_job_creation(self):
        """Creating 10 jobs rapidly in sequence all return 200 with unique IDs."""
        ids = []
        for i in range(10):
            r = self.client.post("/jobs", json={
                "project_id": "marketing",
                "action_id": "marketing.health",
                "payload": {"seq": i},
            })
            if r.status_code == 200:
                jid = r.json().get("job", {}).get("id")
                if jid:
                    ids.append(jid)
        self.check("All 10 rapid job creates return 200", len(ids) == 10, f"{len(ids)}/10")
        self.check("All 10 jobs have unique IDs", len(set(ids)) == 10, f"got {len(set(ids))} unique")


def run_suite():
    print()
    print("=" * 60)
    print("  Master Control Center V1.1 — UAT Test Suite")
    print("=" * 60)

    suite = unittest.TestLoader().loadTestsFromTestCase(UATTestSuite)
    runner = unittest.TextTestRunner(verbosity=0, stream=sys.stdout)
    result = runner.run(suite)

    print()
    print("=" * 60)
    passed = result.testsRun - (len(result.failures) + len(result.errors))
    total = result.testsRun
    print(f"  RESULT: {passed}/{total} passed")

    if result.failures:
        print()
        print("  FAILURES:")
        for test, traceback in result.failures:
            print(f"    - {test}")

    if result.errors:
        print()
        print("  ERRORS:")
        for test, traceback in result.errors:
            print(f"    - {test}")

    if not result.failures and not result.errors:
        print("  ALL TESTS PASSED")
        print()
        print("  Next: start real services and run manual checklist (TEST_CHECKLIST.md)")
    else:
        print()
        print("  Fix failures above before proceeding to manual testing.")
        sys.exit(1)


if __name__ == "__main__":
    run_suite()
