from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from engine import WorkflowEngine
from models import (
    HandoffNotFoundError,
    HandoffState,
    InvalidStateTransitionError,
    MissingInputsError,
    RouteNotFoundError,
)

SALES_INPUTS = ("lead_profile", "deal_status", "target_kpi")
ACCOUNT_INPUTS = ("project_brief", "client_constraints", "budget")


@pytest.fixture
def engine():
    return WorkflowEngine()


@pytest.fixture
def draft(engine):
    """A fresh DRAFT handoff."""
    return engine.initiate("sales", "account", SALES_INPUTS)


# ------------------------------------------------------------------ #
# initiate                                                             #
# ------------------------------------------------------------------ #

def test_initiate_creates_draft(engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    assert h.state == HandoffState.DRAFT
    assert h.id


def test_initiate_missing_inputs_raises(engine):
    with pytest.raises(MissingInputsError, match="Missing required inputs"):
        engine.initiate("sales", "account", ("lead_profile",))


def test_initiate_unknown_route_raises(engine):
    with pytest.raises(RouteNotFoundError):
        engine.initiate("sales", "data", ("foo",))


def test_initiate_stores_provided_inputs(engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    assert h.provided_inputs == SALES_INPUTS


# ------------------------------------------------------------------ #
# approve                                                              #
# ------------------------------------------------------------------ #

def test_approve_transitions_to_approved(engine, draft):
    engine.approve(draft.id)
    assert draft.state == HandoffState.APPROVED


def test_approve_updates_timestamp(engine, draft):
    before = draft.updated_at
    engine.approve(draft.id)
    assert draft.updated_at >= before


def test_cannot_approve_already_approved(engine, draft):
    engine.approve(draft.id)
    with pytest.raises(InvalidStateTransitionError):
        engine.approve(draft.id)


def test_cannot_approve_blocked(engine, draft):
    engine.block(draft.id)
    with pytest.raises(InvalidStateTransitionError):
        engine.approve(draft.id)


def test_approve_unknown_id_raises(engine):
    with pytest.raises(HandoffNotFoundError):
        engine.approve("non-existent-id")


# ------------------------------------------------------------------ #
# block                                                                #
# ------------------------------------------------------------------ #

def test_block_transitions_to_blocked(engine, draft):
    engine.block(draft.id, reason="Client unresponsive")
    assert draft.state == HandoffState.BLOCKED
    assert draft.notes == "Client unresponsive"


def test_cannot_block_approved(engine, draft):
    engine.approve(draft.id)
    with pytest.raises(InvalidStateTransitionError):
        engine.block(draft.id)


def test_cannot_block_already_blocked(engine, draft):
    engine.block(draft.id, reason="first")
    with pytest.raises(InvalidStateTransitionError):
        engine.block(draft.id, reason="second")


def test_block_unknown_id_raises(engine):
    with pytest.raises(HandoffNotFoundError):
        engine.block("non-existent-id")


def test_block_without_reason_leaves_empty_notes(engine, draft):
    engine.block(draft.id)
    assert draft.notes == ""


# ------------------------------------------------------------------ #
# refresh_overdue                                                      #
# ------------------------------------------------------------------ #

def test_refresh_overdue_marks_past_sla(engine, draft):
    future = datetime.utcnow() + timedelta(hours=9)  # SLA is 8h
    flagged = engine.refresh_overdue(now=future)
    assert draft in flagged
    assert draft.state == HandoffState.OVERDUE


def test_approved_not_marked_overdue(engine, draft):
    engine.approve(draft.id)
    future = datetime.utcnow() + timedelta(hours=9)
    flagged = engine.refresh_overdue(now=future)
    assert draft not in flagged
    assert draft.state == HandoffState.APPROVED


def test_not_overdue_within_sla(engine, draft):
    future = datetime.utcnow() + timedelta(hours=4)
    flagged = engine.refresh_overdue(now=future)
    assert draft not in flagged
    assert draft.state == HandoffState.DRAFT


def test_overdue_can_be_approved(engine, draft):
    future = datetime.utcnow() + timedelta(hours=9)
    engine.refresh_overdue(now=future)
    assert draft.state == HandoffState.OVERDUE
    engine.approve(draft.id)
    assert draft.state == HandoffState.APPROVED


def test_blocked_handoff_not_marked_overdue(engine, draft):
    engine.block(draft.id)
    future = datetime.utcnow() + timedelta(hours=9)
    flagged = engine.refresh_overdue(now=future)
    assert draft not in flagged
    assert draft.state == HandoffState.BLOCKED


# ------------------------------------------------------------------ #
# status / get_by_state / all_handoffs                                #
# ------------------------------------------------------------------ #

def test_status_summary(engine):
    engine.initiate("sales", "account", SALES_INPUTS)
    engine.initiate("account", "strategy", ACCOUNT_INPUTS)
    s = engine.status()
    assert s["draft"] == 2
    assert s["approved"] == 0
    assert s["blocked"] == 0
    assert s["overdue"] == 0


def test_get_by_state(engine, draft):
    engine.approve(draft.id)
    assert draft not in engine.get_by_state(HandoffState.DRAFT)
    assert draft in engine.get_by_state(HandoffState.APPROVED)


def test_all_handoffs_empty_on_new_engine(engine):
    assert engine.all_handoffs() == []


def test_all_handoffs_returns_all(engine):
    h1 = engine.initiate("sales", "account", SALES_INPUTS)
    h2 = engine.initiate("account", "strategy", ACCOUNT_INPUTS)
    all_ = engine.all_handoffs()
    assert h1 in all_
    assert h2 in all_


def test_multiple_handoffs_independent(engine):
    h1 = engine.initiate("sales", "account", SALES_INPUTS)
    h2 = engine.initiate("account", "strategy", ACCOUNT_INPUTS)
    engine.approve(h1.id)
    assert h1.state == HandoffState.APPROVED
    assert h2.state == HandoffState.DRAFT


# ------------------------------------------------------------------ #
# get_handoff                                                          #
# ------------------------------------------------------------------ #

def test_get_handoff_returns_instance(engine, draft):
    fetched = engine.get_handoff(draft.id)
    assert fetched is draft


def test_get_handoff_unknown_raises(engine):
    with pytest.raises(HandoffNotFoundError):
        engine.get_handoff("does-not-exist")


# ------------------------------------------------------------------ #
# list_routes                                                          #
# ------------------------------------------------------------------ #

def test_list_routes_returns_all_policies(engine):
    routes = engine.list_routes()
    assert len(routes) > 0
    pairs = {(p.from_department, p.to_department) for p in routes}
    assert ("sales", "account") in pairs


# ------------------------------------------------------------------ #
# restore / export_handoffs round-trip                                #
# ------------------------------------------------------------------ #

def test_export_restore_roundtrip(engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    engine.approve(h.id)

    snapshot = engine.export_handoffs()

    fresh = WorkflowEngine()
    fresh.restore(snapshot)

    restored = fresh.get_handoff(h.id)
    assert restored.id == h.id
    assert restored.state == HandoffState.APPROVED
    assert restored.provided_inputs == SALES_INPUTS
    assert restored.policy.from_department == "sales"


def test_restore_empty_dict_clears_engine(engine, draft):
    engine.restore({})
    assert engine.all_handoffs() == []


def test_export_handoffs_is_copy_of_dict(engine, draft):
    """export_handoffs() returns a separate dict — adding to it does not affect the engine."""
    snapshot = engine.export_handoffs()
    snapshot["fake-id"] = draft  # mutate the returned dict
    assert "fake-id" not in engine.export_handoffs()  # engine dict is untouched
