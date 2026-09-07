"""HTTP API for Drift's idea laboratory and project intelligence."""

from __future__ import annotations

from fastapi import APIRouter, Request

from drift.organism import DriftEvent, DriftLedger, Project, git_snapshot, update_drift_md

router = APIRouter(prefix="/api/organism", tags=["organism"])


def _ledger(request: Request) -> DriftLedger:
    brain = request.app.state.drift_brains.get(request.query_params.get("crab", ""))
    if brain is None:
        brain = next(iter(request.app.state.drift_brains.values()))
    return DriftLedger(brain.env_path)


def _brain(request: Request):
    brains = request.app.state.drift_brains
    key = request.query_params.get("crab")
    return brains.get(key) if key else next(iter(brains.values()))


@router.get("/overview")
async def overview(request: Request):
    ledger = _ledger(request)
    return {
        "ideas": ledger.data["ideas"][-100:],
        "projects": ledger.data["projects"],
        "mind_map": ledger.data["mind_map"],
        "events": ledger.data["events"][-100:],
    }


@router.post("/ideas")
async def capture_idea(request: Request):
    body = await request.json()
    text = str(body.get("text", "")).strip()
    if not text:
        return {"ok": False, "error": "text is required"}
    idea = _ledger(request).add_idea(text, body.get("concepts") or [])
    return {"ok": True, "idea": idea.__dict__}


@router.post("/projects")
async def register_project(request: Request):
    body = await request.json()
    project = Project(
        id=str(body.get("id") or body.get("name", "project")).lower().replace(" ", "-"),
        name=str(body.get("name") or "Unnamed project"),
        repo=str(body.get("repo") or ""),
        local_path=body.get("local_path"),
        importance=float(body.get("importance", 0.5)),
    )
    ledger = _ledger(request)
    ledger.add_project(project)
    return {"ok": True, "project": project.__dict__}


@router.get("/projects/{project_id}/git")
async def project_git(request: Request, project_id: str):
    ledger = _ledger(request)
    project = next((p for p in ledger.data["projects"] if p["id"] == project_id), None)
    if not project or not project.get("local_path"):
        return {"ok": False, "error": "project or local_path not registered"}
    return {"ok": True, "snapshot": git_snapshot(project["local_path"])}


@router.post("/events")
async def add_event(request: Request):
    body = await request.json()
    event = DriftEvent(
        kind=str(body.get("kind", "observation")),
        source=str(body.get("source", "drift")),
        summary=str(body.get("summary", "")),
        confidence=float(body.get("confidence", 0.5)),
        evidence=list(body.get("evidence") or []),
        related_projects=list(body.get("related_projects") or []),
        related_ideas=list(body.get("related_ideas") or []),
    )
    _ledger(request).add_event(event)
    return {"ok": True, "event": event.__dict__}


@router.post("/projects/{project_id}/drift-md")
async def write_project_intelligence(request: Request, project_id: str):
    ledger = _ledger(request)
    project = next((p for p in ledger.data["projects"] if p["id"] == project_id), None)
    if not project or not project.get("local_path"):
        return {"ok": False, "error": "project or local_path not registered"}
    body = await request.json()
    update_drift_md(
        project["local_path"],
        state=str(body.get("state", "")),
        findings=list(body.get("findings") or []),
        challenges=list(body.get("challenges") or []),
        alternatives=list(body.get("alternatives") or []),
    )
    return {"ok": True, "path": f"{project['local_path']}/drift.md"}
