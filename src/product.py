from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from models import Client, Project


class ProductManager:
    def __init__(self, clients: list[Client] | None = None, projects: list[Project] | None = None):
        self._clients = clients or []
        self._projects = projects or []

    def create_client(self, name: str, industry: str) -> Client:
        client = Client(id=str(uuid4()), name=name, industry=industry, created_at=datetime.now(timezone.utc))
        self._clients.append(client)
        return client

    def list_clients(self) -> list[Client]:
        return list(self._clients)

    def create_project(self, client_id: str, name: str, objective: str, owner: str) -> Project:
        if client_id not in {c.id for c in self._clients}:
            raise ValueError(f"Client not found: {client_id}")
        project = Project(
            id=str(uuid4()),
            client_id=client_id,
            name=name,
            objective=objective,
            owner=owner,
            created_at=datetime.now(timezone.utc),
        )
        self._projects.append(project)
        return project

    def list_projects(self, client_id: str | None = None) -> list[Project]:
        if not client_id:
            return list(self._projects)
        return [p for p in self._projects if p.client_id == client_id]

    def get_project(self, project_id: str) -> Project:
        for project in self._projects:
            if project.id == project_id:
                return project
        raise KeyError(f"Project not found: {project_id}")
