from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ai.orchestrator import AutonomousAgency
from engine import WorkflowEngine
from policies import POLICIES
from store import JsonStore

app = FastAPI(title="Agency Workflow API")
store = JsonStore()
engine = WorkflowEngine(POLICIES, handoffs=store.load())
autonomous = AutonomousAgency(existing_tasks=store.load_tasks())


class InitiateRequest(BaseModel):
    from_department: str
    to_department: str
    payload: dict[str, str] = Field(default_factory=dict)


class ActionRequest(BaseModel):
    notes: str = ""


class CreateTaskRequest(BaseModel):
    department: str
    goal: str
    kpi: str
    deadline: str
    context: dict[str, str] = Field(default_factory=dict)


@app.post("/handoffs")
def create_handoff(req: InitiateRequest):
    try:
        handoff = engine.initiate_handoff(req.from_department, req.to_department, req.payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save(engine.list_handoffs())
    return {"id": handoff.id, "state": handoff.state.value}


@app.get("/handoffs")
def list_handoffs():
    return engine.export_handoffs()


@app.get("/handoffs/{handoff_id}")
def get_handoff(handoff_id: str):
    try:
        handoff = engine.get_handoff(handoff_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "id": handoff.id,
        "from_department": handoff.from_department,
        "to_department": handoff.to_department,
        "input_payload": handoff.input_payload,
        "state": handoff.state.value,
        "notes": handoff.notes,
    }


@app.patch("/handoffs/{handoff_id}/approve")
def approve_handoff(handoff_id: str, req: ActionRequest):
    try:
        handoff = engine.approve(handoff_id, req.notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.save(engine.list_handoffs())
    return {"id": handoff.id, "state": handoff.state.value}


@app.patch("/handoffs/{handoff_id}/block")
def block_handoff(handoff_id: str, req: ActionRequest):
    try:
        handoff = engine.block(handoff_id, req.notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.save(engine.list_handoffs())
    return {"id": handoff.id, "state": handoff.state.value}


@app.post("/handoffs/refresh-overdue")
def refresh_overdue():
    updated = engine.refresh_overdue()
    store.save(engine.list_handoffs())
    return {"updated": updated}


@app.get("/status")
def status():
    return engine.status_dashboard()


@app.get("/routes")
def routes():
    return engine.list_routes()


@app.post("/ai/tasks")
def create_ai_task(req: CreateTaskRequest):
    try:
        task = autonomous.create_task(
            goal=req.goal,
            kpi=req.kpi,
            deadline=req.deadline,
            department=req.department,
            context=req.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save_tasks(autonomous.list_tasks())
    return {"id": task.id, "status": task.status.value}


@app.post("/ai/tasks/{task_id}/run")
def run_ai_task(task_id: str):
    try:
        task = autonomous.run_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.save_tasks(autonomous.list_tasks())
    return {"id": task.id, "status": task.status.value, "score": task.score}


@app.get("/ai/tasks")
def list_ai_tasks():
    return [
        {
            "id": task.id,
            "department": task.department,
            "goal": task.goal,
            "kpi": task.kpi,
            "status": task.status.value,
            "score": task.score,
        }
        for task in autonomous.list_tasks()
    ]


@app.get("/ai/status")
def ai_status():
    return autonomous.status_dashboard()
