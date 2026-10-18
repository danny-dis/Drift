"""HTTP API for Drift's idea laboratory and project intelligence."""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException, Request
from drift.organism import DriftEvent, DriftLedger, Project, git_snapshot, update_drift_md

router = APIRouter(prefix="/api/organism", tags=["organism"])


def _brain(request: Request):
    brains = getattr(request.app.state, "drift_brains", {}) or {}
    if not brains:
        raise HTTPException(status_code=503, detail="No Drift organisms running")
    key = request.query_params.get("crab")
    if key and key in brains:
        return brains[key]
    if key:
        raise HTTPException(status_code=404, detail="organism not found")
    return next(iter(brains.values()))


def _stores(request: Request):
    brain = _brain(request)
    return brain, brain.ledger, brain.tasks


def _register_watch(brain, project: Project) -> None:
    watcher = getattr(brain, "watcher", None)
    if watcher is not None and project.local_path:
        try:
            watcher.register_project(project.id, project.local_path)
        except Exception:
            pass


@router.get("/overview")
async def overview(request: Request):
    brain, ledger, tasks = _stores(request)
    return {"ideas": ledger.data["ideas"][-100:], "projects": ledger.data["projects"], "mind_map": ledger.data["mind_map"], "events": ledger.data["events"][-100:]}


@router.post("/ideas")
async def capture_idea(request: Request):
    from drift.pipeline import capture_idea_unified
    brain, ledger, tasks = _stores(request)
    body = await request.json()
    try:
        idea, _task = capture_idea_unified(
            ledger, tasks, {}, str(body.get("text", "")), body.get("concepts"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "idea": idea.__dict__}


@router.post("/projects")
async def register_project(request: Request):
    from drift.pipeline import register_project_record
    brain, ledger, tasks = _stores(request)
    body = await request.json()
    try:
        project = register_project_record(ledger, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _register_watch(brain, project)
    return {"ok": True, "project": project.__dict__}


@router.get("/projects/{project_id}/git")
async def project_git(request: Request, project_id: str):
    brain, ledger, tasks = _stores(request)
    project = next((p for p in ledger.data["projects"] if p["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if not project.get("local_path"):
        raise HTTPException(status_code=404, detail="project local_path not registered")
    return {"ok": True, "snapshot": git_snapshot(project["local_path"])}


@router.post("/events")
async def add_event(request: Request):
    brain, ledger, tasks = _stores(request)
    body = await request.json()
    event = DriftEvent(kind=str(body.get("kind", "observation")), source=str(body.get("source", "drift")), summary=str(body.get("summary", "")), confidence=float(body.get("confidence", 0.5)), evidence=list(body.get("evidence") or []), related_projects=list(body.get("related_projects") or []), related_ideas=list(body.get("related_ideas") or []))
    ledger.add_event(event)
    return {"ok": True, "event": event.__dict__}


@router.post("/projects/{project_id}/drift-md")
async def write_project_intelligence(request: Request, project_id: str):
    brain, ledger, tasks = _stores(request)
    project = next((p for p in ledger.data["projects"] if p["id"] == project_id), None)
    # Fail closed: only explicitly registered local paths may be written.
    if not project or not project.get("local_path"):
        raise HTTPException(status_code=404, detail="project or local_path not registered")
    body = await request.json()
    try:
        update_drift_md(project["local_path"], state=str(body.get("state", "")), findings=list(body.get("findings") or []), challenges=list(body.get("challenges") or []), alternatives=list(body.get("alternatives") or []))
    except (OSError, ValueError):
        raise HTTPException(409, 'Project document is unsafe or unavailable; inspect drift.md before retrying') from None
    return {"ok": True, "path": f"{project['local_path']}/drift.md"}


@router.post("/identity/animal")
async def set_animal(request: Request):
    brain = _brain(request)
    body = await request.json()
    animal = str(body.get("animal", "")).strip().lower()
    if not animal:
        raise HTTPException(status_code=400, detail="animal is required")
    brain.identity["animal"] = animal
    path = f"{brain.env_path}/identity.json"
    with open(path, "w") as f:
        json.dump(brain.identity, f, indent=2)
    await brain._broadcast({"event": "identity", "data": brain.identity})
    return {"ok": True, "animal": animal}
