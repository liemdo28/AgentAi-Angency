from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from engine import WorkflowEngine
from policies import POLICIES
from product import ProductManager
from store import JsonStore

app = FastAPI(title="Agency Workflow API")
store = JsonStore()
handoffs, clients, projects = store.load_all()
engine = WorkflowEngine(POLICIES, handoffs=handoffs)
product = ProductManager(clients=clients, projects=projects)
API_KEY = os.getenv("AGENCY_API_KEY", "local-dev-key")


class InitiateRequest(BaseModel):
    from_department: str
    to_department: str
    payload: dict[str, str] = Field(default_factory=dict)
    client_id: str | None = None
    project_id: str | None = None


class ActionRequest(BaseModel):
    notes: str = ""


class ClientRequest(BaseModel):
    name: str
    industry: str


class ProjectRequest(BaseModel):
    client_id: str
    name: str
    objective: str
    owner: str


def check_api_key(x_api_key: str | None) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.post("/clients")
def create_client(req: ClientRequest, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    client = product.create_client(req.name, req.industry)
    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return {"id": client.id, "name": client.name, "industry": client.industry}


@app.get("/clients")
def list_clients(x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    return [{"id": c.id, "name": c.name, "industry": c.industry} for c in product.list_clients()]


@app.post("/projects")
def create_project(req: ProjectRequest, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    try:
        project = product.create_project(req.client_id, req.name, req.objective, req.owner)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return {
        "id": project.id,
        "client_id": project.client_id,
        "name": project.name,
        "objective": project.objective,
        "owner": project.owner,
    }


@app.get("/projects")
def list_projects(client_id: str | None = None, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    return [
        {"id": p.id, "client_id": p.client_id, "name": p.name, "objective": p.objective, "owner": p.owner}
        for p in product.list_projects(client_id)
    ]


@app.post("/handoffs")
def create_handoff(req: InitiateRequest, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    try:
        handoff = engine.initiate_handoff(
            req.from_department,
            req.to_department,
            req.payload,
            client_id=req.client_id,
            project_id=req.project_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return {"id": handoff.id, "state": handoff.state.value}


@app.get("/handoffs")
def list_handoffs(project_id: str | None = None, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    if project_id:
        return [
            {
                "id": h.id,
                "from_department": h.from_department,
                "to_department": h.to_department,
                "state": h.state.value,
                "project_id": h.project_id,
            }
            for h in engine.list_by_project(project_id)
        ]
    return engine.export_handoffs()


@app.get("/handoffs/{handoff_id}")
def get_handoff(handoff_id: str, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
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
        "client_id": handoff.client_id,
        "project_id": handoff.project_id,
    }


@app.patch("/handoffs/{handoff_id}/approve")
def approve_handoff(handoff_id: str, req: ActionRequest, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    try:
        handoff = engine.approve(handoff_id, req.notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return {"id": handoff.id, "state": handoff.state.value}


@app.patch("/handoffs/{handoff_id}/block")
def block_handoff(handoff_id: str, req: ActionRequest, x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    try:
        handoff = engine.block(handoff_id, req.notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return {"id": handoff.id, "state": handoff.state.value}


@app.post("/handoffs/refresh-overdue")
def refresh_overdue(x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    updated = engine.refresh_overdue()
    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return {"updated": updated}


@app.get("/status")
def status(x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    dashboard = engine.status_dashboard()
    dashboard["clients"] = len(product.list_clients())
    dashboard["projects"] = len(product.list_projects())
    return dashboard


@app.get("/routes")
def routes(x_api_key: str | None = Header(default=None)):
    check_api_key(x_api_key)
    return engine.list_routes()
