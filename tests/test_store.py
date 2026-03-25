"""Tests for src/store.py — persistence, atomic writes, error handling."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

import store
from engine import WorkflowEngine
from models import HandoffState

SALES_INPUTS = ("lead_profile", "deal_status", "target_kpi")


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Redirect all store I/O to a temp file so tests don't pollute the repo."""
    state_file = tmp_path / "test_state.json"
    monkeypatch.setattr(store, "STATE_FILE", state_file)
    return state_file


@pytest.fixture
def engine():
    return WorkflowEngine()


# ------------------------------------------------------------------ #
# load                                                                 #
# ------------------------------------------------------------------ #

def test_load_returns_empty_when_no_file(tmp_state):
    assert store.load() == {}


def test_load_returns_empty_for_empty_json(tmp_state):
    tmp_state.write_text("{}", encoding="utf-8")
    assert store.load() == {}


def test_load_raises_on_corrupt_json(tmp_state):
    tmp_state.write_text("not valid json {{{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Failed to load state"):
        store.load()


def test_load_skips_corrupted_entries_with_warning(tmp_state):
    """A valid handoff and one broken entry: valid one loads, broken is skipped."""
    eng = WorkflowEngine()
    h = eng.initiate("sales", "account", SALES_INPUTS)
    store.save(eng.export_handoffs())

    # Inject a malformed entry alongside the valid one
    raw = json.loads(tmp_state.read_text())
    raw["bad-id"] = {"broken": True}
    tmp_state.write_text(json.dumps(raw))

    with pytest.warns(UserWarning):
        result = store.load()

    assert h.id in result
    assert "bad-id" not in result


# ------------------------------------------------------------------ #
# save                                                                 #
# ------------------------------------------------------------------ #

def test_save_creates_file(tmp_state, engine):
    engine.initiate("sales", "account", SALES_INPUTS)
    store.save(engine.export_handoffs())
    assert tmp_state.exists()


def test_save_produces_valid_json(tmp_state, engine):
    engine.initiate("sales", "account", SALES_INPUTS)
    store.save(engine.export_handoffs())
    data = json.loads(tmp_state.read_text())
    assert isinstance(data, dict)


def test_save_overwrites_previous(tmp_state, engine):
    h1 = engine.initiate("sales", "account", SALES_INPUTS)
    store.save(engine.export_handoffs())

    engine.approve(h1.id)
    store.save(engine.export_handoffs())

    data = json.loads(tmp_state.read_text())
    assert data[h1.id]["state"] == "approved"


# ------------------------------------------------------------------ #
# round-trip: save → load → restore                                   #
# ------------------------------------------------------------------ #

def test_roundtrip_preserves_draft_state(tmp_state, engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    store.save(engine.export_handoffs())

    fresh = WorkflowEngine()
    fresh.restore(store.load())
    restored = fresh.get_handoff(h.id)

    assert restored.id == h.id
    assert restored.state == HandoffState.DRAFT
    assert restored.provided_inputs == SALES_INPUTS


def test_roundtrip_preserves_approved_state(tmp_state, engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    engine.approve(h.id)
    store.save(engine.export_handoffs())

    fresh = WorkflowEngine()
    fresh.restore(store.load())
    restored = fresh.get_handoff(h.id)

    assert restored.state == HandoffState.APPROVED


def test_roundtrip_preserves_blocked_with_notes(tmp_state, engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    engine.block(h.id, reason="Budget frozen")
    store.save(engine.export_handoffs())

    fresh = WorkflowEngine()
    fresh.restore(store.load())
    restored = fresh.get_handoff(h.id)

    assert restored.state == HandoffState.BLOCKED
    assert restored.notes == "Budget frozen"


def test_roundtrip_preserves_timestamps(tmp_state, engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    original_created = h.created_at
    store.save(engine.export_handoffs())

    fresh = WorkflowEngine()
    fresh.restore(store.load())
    restored = fresh.get_handoff(h.id)

    # Timestamps should survive the serialization round-trip
    assert abs((restored.created_at - original_created).total_seconds()) < 0.001


def test_roundtrip_preserves_policy(tmp_state, engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    store.save(engine.export_handoffs())

    fresh = WorkflowEngine()
    fresh.restore(store.load())
    restored = fresh.get_handoff(h.id)

    assert restored.policy.from_department == "sales"
    assert restored.policy.to_department == "account"
    assert restored.policy.sla_hours == 8


def test_roundtrip_multiple_handoffs(tmp_state, engine):
    h1 = engine.initiate("sales", "account", SALES_INPUTS)
    h2 = engine.initiate("account", "strategy",
                         ("project_brief", "client_constraints", "budget"))
    engine.approve(h1.id)
    store.save(engine.export_handoffs())

    fresh = WorkflowEngine()
    fresh.restore(store.load())

    assert fresh.get_handoff(h1.id).state == HandoffState.APPROVED
    assert fresh.get_handoff(h2.id).state == HandoffState.DRAFT


# ------------------------------------------------------------------ #
# handoff_to_dict                                                      #
# ------------------------------------------------------------------ #

def test_handoff_to_dict_contains_required_keys(engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    d = store.handoff_to_dict(h)
    for key in ("id", "state", "created_at", "updated_at", "notes",
                "provided_inputs", "policy"):
        assert key in d


def test_handoff_to_dict_policy_contains_required_keys(engine):
    h = engine.initiate("sales", "account", SALES_INPUTS)
    p = store.handoff_to_dict(h)["policy"]
    for key in ("from_department", "to_department", "required_inputs",
                "expected_outputs", "sla_hours", "approver_role"):
        assert key in p
