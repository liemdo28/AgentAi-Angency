"""
AgentAI Agency — REST API

Run:
  uvicorn src.api:app --reload          (from project root)
  PYTHONPATH=.:src uvicorn api:app --reload --app-dir src

Endpoints:
  POST   /handoffs                       Create a new handoff
  GET    /handoffs                       List handoffs (?state= ?limit= ?offset=)
  GET    /handoffs/{id}                  Get a single handoff
  PATCH  /handoffs/{id}/approve          Approve a handoff
  PATCH  /handoffs/{id}/block            Block a handoff
  POST   /handoffs/refresh-overdue       Mark overdue handoffs
  GET    /status                         Dashboard counts by state
  GET    /routes                         List all available routes
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

import store
from engine import WorkflowEngine
from models import (
    HandoffNotFoundError,
    HandoffState,
    InvalidStateTransitionError,
    MissingInputsError,
    RouteNotFoundError,
)

# ------------------------------------------------------------------ #
# App lifecycle                                                        #
# ------------------------------------------------------------------ #

engine = WorkflowEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.restore(store.load())
    yield


app = FastAPI(
    title="AgentAI Agency",
    description="Runtime workflow engine for inter-department handoffs",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# Request / Response Pydantic schemas                                  #
# ------------------------------------------------------------------ #

class InitiateRequest(BaseModel):
    from_department: str
    to_department: str
    inputs: list[str]

    @field_validator("inputs")
    @classmethod
    def inputs_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("inputs must not be empty")
        return v

    @field_validator("from_department", "to_department")
    @classmethod
    def dept_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("department name must not be blank")
        return v


class BlockRequest(BaseModel):
    reason: str = ""


class PolicyOut(BaseModel):
    from_department: str
    to_department: str
    required_inputs: list[str]
    expected_outputs: list[str]
    sla_hours: int
    approver_role: str


class HandoffOut(BaseModel):
    id: str
    state: str
    created_at: str
    updated_at: str
    notes: str
    provided_inputs: list[str]
    policy: PolicyOut


class HandoffListOut(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[HandoffOut]


class StatusOut(BaseModel):
    draft: int
    approved: int
    blocked: int
    overdue: int


class RefreshOverdueOut(BaseModel):
    flagged_count: int
    ids: list[str]


def _to_handoff_out(h) -> HandoffOut:
    d = store.handoff_to_dict(h)
    return HandoffOut(
        id=d["id"],
        state=d["state"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        notes=d["notes"],
        provided_inputs=d["provided_inputs"],
        policy=PolicyOut(**d["policy"]),
    )


# ------------------------------------------------------------------ #
# Routes                                                               #
# ------------------------------------------------------------------ #

@app.post("/handoffs", status_code=201, response_model=HandoffOut,
          summary="Create a new handoff")
def initiate(req: InitiateRequest):
    try:
        h = engine.initiate(req.from_department, req.to_department, tuple(req.inputs))
        store.save(engine.export_handoffs())
        return _to_handoff_out(h)
    except RouteNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except MissingInputsError as e:
        raise HTTPException(400, detail=str(e))


@app.get("/handoffs", response_model=HandoffListOut,
         summary="List handoffs with optional state filter and pagination")
def list_handoffs(
    state: Optional[str] = Query(None, description="draft | approved | blocked | overdue"),
    limit: int = Query(50, ge=1, le=500, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
):
    if state:
        try:
            s = HandoffState(state)
        except ValueError:
            valid = [v.value for v in HandoffState]
            raise HTTPException(400, detail=f"Invalid state. Valid values: {valid}")
        items = engine.get_by_state(s)
    else:
        items = engine.all_handoffs()

    total = len(items)
    page = items[offset: offset + limit]
    return HandoffListOut(total=total, offset=offset, limit=limit,
                          items=[_to_handoff_out(h) for h in page])


@app.get("/handoffs/{handoff_id}", response_model=HandoffOut,
         summary="Get a single handoff by ID")
def get_handoff(handoff_id: str):
    try:
        h = engine.get_handoff(handoff_id)
        return _to_handoff_out(h)
    except HandoffNotFoundError as e:
        raise HTTPException(404, detail=str(e))


@app.patch("/handoffs/{handoff_id}/approve", response_model=HandoffOut,
           summary="Approve a handoff")
def approve(handoff_id: str):
    try:
        h = engine.approve(handoff_id)
        store.save(engine.export_handoffs())
        return _to_handoff_out(h)
    except HandoffNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(409, detail=str(e))


@app.patch("/handoffs/{handoff_id}/block", response_model=HandoffOut,
           summary="Block a handoff")
def block(handoff_id: str, req: BlockRequest = BlockRequest()):
    try:
        h = engine.block(handoff_id, req.reason)
        store.save(engine.export_handoffs())
        return _to_handoff_out(h)
    except HandoffNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(409, detail=str(e))


@app.post("/handoffs/refresh-overdue", response_model=RefreshOverdueOut,
          summary="Scan and mark all overdue handoffs")
def refresh_overdue():
    flagged = engine.refresh_overdue()
    store.save(engine.export_handoffs())
    return RefreshOverdueOut(flagged_count=len(flagged), ids=[h.id for h in flagged])


@app.get("/status", response_model=StatusOut,
         summary="Dashboard: handoff counts per state")
def status():
    return engine.status()


@app.get("/routes", summary="List all available department routes")
def routes():
    return [
        {
            "from": p.from_department,
            "to": p.to_department,
            "sla_hours": p.sla_hours,
            "approver_role": p.approver_role,
            "required_inputs": list(p.required_inputs),
            "expected_outputs": list(p.expected_outputs),
        }
        for p in engine.list_routes()
    ]
