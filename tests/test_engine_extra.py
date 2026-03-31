"""
Stream A gaps — tests not covered by test_engine.py.

Covers:
  A3. Overdue boundary: exactly-at-SLA, 1s before, 1s after
  A4. Concurrency: thread-safe create, approve/block race, refresh_overdue parallel
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from engine import WorkflowEngine
from models import HandoffState

SALES_INPUTS = ("lead_profile", "deal_status", "target_kpi")


# ------------------------------------------------------------------ #
# A3. Overdue Boundary                                                 #
# ------------------------------------------------------------------ #
# is_overdue() uses: now_dt > deadline  (strict greater-than)
# deadline = created_at + timedelta(hours=sla_hours)
# sales→account SLA = 8 hours


class TestOverdueBoundary:
    @pytest.fixture
    def engine(self):
        return WorkflowEngine()

    @pytest.fixture
    def draft(self, engine):
        return engine.initiate("sales", "account", SALES_INPUTS)

    def test_exactly_at_deadline_not_overdue(self, engine, draft):
        """At T+8h exactly: now_dt == deadline → not overdue (strict >)."""
        exactly_at = draft.created_at + timedelta(hours=8)
        flagged = engine.refresh_overdue(now=exactly_at)
        assert draft not in flagged
        assert draft.state == HandoffState.DRAFT

    def test_one_second_past_deadline_is_overdue(self, engine, draft):
        """At T+8h+1s: now_dt > deadline → overdue."""
        one_past = draft.created_at + timedelta(hours=8, seconds=1)
        flagged = engine.refresh_overdue(now=one_past)
        assert draft in flagged
        assert draft.state == HandoffState.OVERDUE

    def test_one_second_before_deadline_not_overdue(self, engine, draft):
        """At T+8h-1s: not yet overdue."""
        one_before = draft.created_at + timedelta(hours=8) - timedelta(seconds=1)
        flagged = engine.refresh_overdue(now=one_before)
        assert draft not in flagged
        assert draft.state == HandoffState.DRAFT

    def test_refresh_overdue_idempotent_on_already_overdue(self, engine, draft):
        """Calling refresh_overdue twice on an already-overdue handoff does not crash."""
        future = draft.created_at + timedelta(hours=9)
        engine.refresh_overdue(now=future)
        assert draft.state == HandoffState.OVERDUE
        # Second call — should skip (OVERDUE is no longer DRAFT)
        flagged2 = engine.refresh_overdue(now=future)
        assert draft not in flagged2
        assert draft.state == HandoffState.OVERDUE

    def test_approved_handoff_never_becomes_overdue(self, engine, draft):
        """An APPROVED handoff must not be re-flagged as OVERDUE."""
        engine.approve(draft.id)
        far_future = draft.created_at + timedelta(hours=100)
        flagged = engine.refresh_overdue(now=far_future)
        assert draft not in flagged
        assert draft.state == HandoffState.APPROVED

    def test_mixed_states_only_draft_flagged(self, engine):
        """Only DRAFT handoffs past SLA are flagged; others stay put."""
        d1 = engine.initiate("sales", "account", SALES_INPUTS)
        d2 = engine.initiate("account", "strategy",
                             ("project_brief", "client_constraints", "budget"))
        engine.approve(d2.id)

        far_future = datetime.now(timezone.utc) + timedelta(hours=24)
        flagged = engine.refresh_overdue(now=far_future)

        assert d1 in flagged
        assert d2 not in flagged
        assert d2.state == HandoffState.APPROVED


# ------------------------------------------------------------------ #
# A4. Concurrency                                                      #
# ------------------------------------------------------------------ #

class TestConcurrency:
    def test_concurrent_initiate_no_lost_records(self):
        """50 threads each create one handoff — all 50 must be stored."""
        engine = WorkflowEngine()
        ids: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def create():
            try:
                h = engine.initiate("sales", "account", SALES_INPUTS)
                with lock:
                    ids.append(h.id)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=create) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Unexpected errors: {errors}"
        assert len(ids) == 50
        assert len(engine.all_handoffs()) == 50
        assert len(set(ids)) == 50  # all IDs are unique

    def test_concurrent_approve_block_exactly_one_wins(self):
        """Two threads race to approve vs block the same handoff — exactly one wins."""
        engine = WorkflowEngine()
        draft = engine.initiate("sales", "account", SALES_INPUTS)

        outcomes: list[str] = []
        lock = threading.Lock()

        def try_approve():
            try:
                engine.approve(draft.id)
                with lock:
                    outcomes.append("approved")
            except Exception:
                with lock:
                    outcomes.append("approve_failed")

        def try_block():
            try:
                engine.block(draft.id, reason="concurrent block")
                with lock:
                    outcomes.append("blocked")
            except Exception:
                with lock:
                    outcomes.append("block_failed")

        t1 = threading.Thread(target=try_approve)
        t2 = threading.Thread(target=try_block)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # The handoff must be in a valid final state
        assert draft.state in (HandoffState.APPROVED, HandoffState.BLOCKED)
        # Exactly one operation succeeded
        success = [o for o in outcomes if o in ("approved", "blocked")]
        assert len(success) == 1

    def test_concurrent_refresh_overdue_no_double_transition(self):
        """10 threads refresh_overdue simultaneously — no corruption or crash."""
        engine = WorkflowEngine()
        for _ in range(10):
            engine.initiate("sales", "account", SALES_INPUTS)

        future = datetime.now(timezone.utc) + timedelta(hours=9)
        exceptions: list[str] = []
        lock = threading.Lock()

        def refresh():
            try:
                engine.refresh_overdue(now=future)
            except Exception as exc:
                with lock:
                    exceptions.append(str(exc))

        threads = [threading.Thread(target=refresh) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not exceptions, f"Exceptions during concurrent refresh: {exceptions}"
        # All handoffs should be OVERDUE — no handoff left in DRAFT
        states = {h.state for h in engine.all_handoffs()}
        assert HandoffState.DRAFT not in states
        assert HandoffState.OVERDUE in states

    def test_concurrent_create_and_list_no_crash(self):
        """Writers and readers running simultaneously must not crash."""
        engine = WorkflowEngine()
        errors: list[str] = []
        lock = threading.Lock()

        def writer():
            try:
                engine.initiate("sales", "account", SALES_INPUTS)
            except Exception as exc:
                with lock:
                    errors.append(f"writer: {exc}")

        def reader():
            try:
                engine.all_handoffs()
                engine.status()
            except Exception as exc:
                with lock:
                    errors.append(f"reader: {exc}")

        threads = (
            [threading.Thread(target=writer) for _ in range(20)]
            + [threading.Thread(target=reader) for _ in range(20)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent read/write errors: {errors}"
