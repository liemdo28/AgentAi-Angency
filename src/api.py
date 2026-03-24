"""
AgentAI Agency — REST API

Run:
  uvicorn src.api:app --reload          (from project root)
  PYTHONPATH=.:src uvicorn api:app --reload --app-dir src

Endpoints:
  POST   /handoffs                       Create a new handoff
  GET    /handoffs                       List all handoffs (optional ?state=)
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
from pydantic import BaseModel, field_validator

import store
from engine import WorkflowEngine
from models import HandoffState

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
    version="1.0.0",
    lifespan=lifespan,
)

# ------------------------------------------------------------------ #
# Pydantic schemas                                                     #
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


class BlockRequest(BaseModel):
    reason: str = ""


def _handoff_response(h) -> dict:
    d = store.handoff_to_dict(h)
    return d


# ------------------------------------------------------------------ #
# Routes                                                               #
# ------------------------------------------------------------------ #

@app.post("/handoffs", status_code=201, summary="Create a new handoff")
def initiate(req: InitiateRequest):
    try:
        h = engine.initiate(req.from_department, req.to_department, tuple(req.inputs))
        store.save(engine.export_handoffs())
        return _handoff_response(h)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    except ValueError as e:
        raise HTTPException(400, detail=str(e))


@app.get("/handoffs", summary="List handoffs (optional ?state= filter)")

def list_handoffs(state: Optional[str] = Query(None, description="draft|approved|blocked|overdue")):
    if state:
        try:
            s = HandoffState(state)
        except ValueError:
            valid = [v.value for v in HandoffState]
            raise HTTPException(400, detail=f"Invalid state. Valid values: {valid}")
        items = engine.get_by_state(s)
    else:
        items = engine.all_handoffs()
    return [_handoff_response(h) for h in items]


@app.get("/handoffs/{handoff_id}", summary="Get a single handoff by ID")
def get_handoff(handoff_id: str):
    try:
        h = engine.get_handoff(handoff_id)
        return _handoff_response(h)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))


@app.patch("/handoffs/{handoff_id}/approve", summary="Approve a handoff")
def approve(handoff_id: str):
    try:
        h = engine.approve(handoff_id)
        store.save(engine.export_handoffs())
        return _handoff_response(h)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    except ValueError as e:
        raise HTTPException(409, detail=str(e))


@app.patch("/handoffs/{handoff_id}/block", summary="Block a handoff")
def block(handoff_id: str, req: BlockRequest = BlockRequest()):
    try:
        h = engine.block(handoff_id, req.reason)
        store.save(engine.export_handoffs())
        return _handoff_response(h)
    except KeyError as e:
        raise HTTPException(404, detail=str(e))
    except ValueError as e:
        raise HTTPException(409, detail=str(e))


@app.post("/handoffs/refresh-overdue", summary="Scan and mark overdue handoffs")
def refresh_overdue():
    flagged = engine.refresh_overdue()
    store.save(engine._handoffs)
    return {
        "flagged_count": len(flagged),
        "ids": [h.id for h in flagged],
    }


@app.get("/status", summary="Dashboard: handoff counts by state")
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
