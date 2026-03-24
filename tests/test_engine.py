from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine import WorkflowEngine
from models import HandoffState


@pytest.fixture
def engine():
    return WorkflowEngine()


# ------------------------------------------------------------------ #
# initiate                                                             #
# ------------------------------------------------------------------ #

def test_initiate_creates_draft(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    assert h.state == HandoffState.DRAFT
    assert h.id


def test_initiate_missing_inputs_raises(engine):
    with pytest.raises(ValueError, match="Missing required inputs"):
        engine.initiate("sales", "account", ("lead_profile",))


def test_initiate_unknown_route_raises(engine):
    with pytest.raises(KeyError):
        engine.initiate("sales", "data", ("foo",))


def test_initiate_stores_provided_inputs(engine):
    inputs = ("lead_profile", "deal_status", "target_kpi")
    h = engine.initiate("sales", "account", inputs)
    assert h.provided_inputs == inputs


# ------------------------------------------------------------------ #
# approve                                                              #
# ------------------------------------------------------------------ #

def test_approve_transitions_to_approved(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.approve(h.id)
    assert h.state == HandoffState.APPROVED


def test_approve_updates_timestamp(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    before = h.updated_at
    engine.approve(h.id)
    assert h.updated_at >= before


def test_cannot_approve_already_approved(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.approve(h.id)
    with pytest.raises(ValueError):
        engine.approve(h.id)


def test_cannot_approve_blocked(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.block(h.id)
    with pytest.raises(ValueError):
        engine.approve(h.id)


# ------------------------------------------------------------------ #
# block                                                                #
# ------------------------------------------------------------------ #

def test_block_transitions_to_blocked(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.block(h.id, reason="Client unresponsive")
    assert h.state == HandoffState.BLOCKED
    assert h.notes == "Client unresponsive"


def test_cannot_block_approved(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.approve(h.id)
    with pytest.raises(ValueError):
        engine.block(h.id)


# ------------------------------------------------------------------ #
# refresh_overdue                                                      #
# ------------------------------------------------------------------ #

def test_refresh_overdue_marks_past_sla(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    future = datetime.utcnow() + timedelta(hours=9)  # SLA is 8h
    flagged = engine.refresh_overdue(now=future)
    assert h in flagged
    assert h.state == HandoffState.OVERDUE


def test_approved_not_marked_overdue(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.approve(h.id)
    future = datetime.utcnow() + timedelta(hours=9)
    flagged = engine.refresh_overdue(now=future)
    assert h not in flagged
    assert h.state == HandoffState.APPROVED


def test_not_overdue_within_sla(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    future = datetime.utcnow() + timedelta(hours=4)  # SLA is 8h, still within
    flagged = engine.refresh_overdue(now=future)
    assert h not in flagged
    assert h.state == HandoffState.DRAFT


def test_overdue_can_be_approved(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    future = datetime.utcnow() + timedelta(hours=9)
    engine.refresh_overdue(now=future)
    assert h.state == HandoffState.OVERDUE
    engine.approve(h.id)
    assert h.state == HandoffState.APPROVED


# ------------------------------------------------------------------ #
# status / get_by_state                                               #
# ------------------------------------------------------------------ #

def test_status_summary(engine):
    engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.initiate("account", "strategy", ("project_brief", "client_constraints", "budget"))
    s = engine.status()
    assert s["draft"] == 2
    assert s["approved"] == 0
    assert s["blocked"] == 0
    assert s["overdue"] == 0


def test_get_by_state(engine):
    h = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    engine.approve(h.id)
    assert h not in engine.get_by_state(HandoffState.DRAFT)
    assert h in engine.get_by_state(HandoffState.APPROVED)


def test_multiple_handoffs_independent(engine):
    h1 = engine.initiate("sales", "account", ("lead_profile", "deal_status", "target_kpi"))
    h2 = engine.initiate("account", "strategy", ("project_brief", "client_constraints", "budget"))
    engine.approve(h1.id)
    assert h1.state == HandoffState.APPROVED
    assert h2.state == HandoffState.DRAFT
