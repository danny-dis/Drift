"""Production UI API endpoints for Drift (Phase 7).

Adds REST endpoints for: project shelf, idea inbox, research view,
budget dashboard, context receipts, approval center, and notifications.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from drift.brain import Brain
from drift.config import config

logger = logging.getLogger("drift.ui_api")

router = APIRouter(prefix="/api/ui", tags=["ui"])


def _get_brain(request: Request) -> Brain:
    """Get the brain instance from the app state."""
    brains = getattr(request.app.state, "drift_brains", {}) or {}
    if not brains:
        raise HTTPException(status_code=503, detail="No Drift organisms running")
    crab_id = request.query_params.get("crab")
    if crab_id and crab_id in brains:
        return brains[crab_id]
    if crab_id:
        raise HTTPException(status_code=404, detail="organism not found")
    return next(iter(brains.values()))


@router.get("/tasks")
async def list_tasks(request: Request):
    from dataclasses import asdict
    return {"tasks": [asdict(t) for t in _get_brain(request).tasks.list_tasks()[-100:]]}


@router.get("/tasks/{task_id}/report")
async def read_task_report(task_id: str, request: Request):
    from pathlib import Path
    brain = _get_brain(request)
    task = brain.tasks.get_task(task_id)
    root = Path(brain.env_path).resolve()
    path = Path(task.last_evidence).resolve() if task and task.last_evidence else root
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="report not available")
    with path.open(encoding="utf-8") as f:
        text = f.read(12001)
    return {"task_id": task_id, "text": text[:12000], "truncated": len(text) > 12000}


# ---------------------------------------------------------------------------
# Project shelf
# ---------------------------------------------------------------------------

@router.get("/projects")
async def list_projects(request: Request):
    """List all projects with their status."""
    brain = _get_brain(request)
    projects = []
    for p in brain.ledger.data.get("projects", []):
        projects.append({
            "id": p["id"],
            "name": p.get("name", ""),
            "repo": p.get("repo", ""),
            "local_path": p.get("local_path", ""),
            "last_seen_commit": p.get("last_seen_commit", ""),
            "last_round": p.get("last_round", ""),
        })
    return {"projects": projects}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    """Get a single project with its intelligence and recent events."""
    brain = _get_brain(request)
    project = next(
        (p for p in brain.ledger.data.get("projects", []) if p["id"] == project_id),
        None,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get related events
    events = [
        e for e in brain.ledger.data.get("events", [])
        if project_id in e.get("related_projects", [])
    ]

    # Get related ideas
    ideas = [
        i for i in brain.ledger.data.get("ideas", [])
        if project_id in i.get("related_projects", [])
    ]

    # Get drift.md if available
    drift_md = ""
    if project.get("local_path"):
        from drift.organism import read_drift_md
        drift_md = read_drift_md(project["local_path"])

    return {
        "project": project,
        "events": events[-20:],  # Last 20 events
        "ideas": ideas[-10:],
        "drift_md": drift_md,
        "intelligence": project.get("intelligence"),
    }


# ---------------------------------------------------------------------------
# Idea inbox
# ---------------------------------------------------------------------------

@router.get("/ideas")
async def list_ideas(request: Request, status: str | None = None):
    """List all ideas, optionally filtered by status."""
    brain = _get_brain(request)
    ideas = brain.ledger.data.get("ideas", [])
    if status:
        ideas = [i for i in ideas if i.get("status", "captured") == status]
    return {"ideas": ideas}


@router.post("/ideas")
async def create_idea(request: Request):
    """Create a new idea from text (unified with organism route)."""
    brain = _get_brain(request)
    body = await request.json()
    from drift.pipeline import capture_idea_unified
    try:
        idea, _task = capture_idea_unified(
            brain.ledger, brain.tasks, {}, body.get("text", ""),
            body.get("concepts"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"idea": {"id": idea.id, "text": idea.text, "concepts": idea.concepts, "status": idea.status}}


@router.post("/projects")
async def create_project(request: Request):
    """Register a project (reuses organism route logic + watch)."""
    brain = _get_brain(request)
    body = await request.json()
    from drift.pipeline import register_project_record
    try:
        project = register_project_record(brain.ledger, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    watcher = getattr(brain, "watcher", None)
    if watcher is not None and project.local_path:
        try:
            watcher.register_project(project.id, project.local_path)
        except Exception:
            pass
    return {"ok": True, "project": project.__dict__}


@router.post("/ideas/{idea_id}/qualify")
async def qualify_idea(idea_id: str, request: Request):
    """Qualify an idea as PROJECT, RESEARCH, or PARKED."""
    brain = _get_brain(request)
    body = await request.json()
    qualification = body.get("qualification", "").upper()

    from drift.pipeline import IdeaPipeline
    pipeline = IdeaPipeline(brain.ledger, brain.tasks, {})
    try:
        idea = pipeline.qualify_idea(idea_id, qualification)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"idea": {"id": idea.id, "status": idea.status}}


# ---------------------------------------------------------------------------
# Research sessions (state-lane seam; lazy import so controller wiring stays free)
# ---------------------------------------------------------------------------

@router.get("/research/sessions")
async def list_research_sessions(request: Request):
    """List durable research sessions."""
    from drift.research import ResearchStore
    brain = _get_brain(request)
    store = ResearchStore(brain.env_path)
    return {"sessions": store.list()}


@router.post("/research/sessions")
async def create_research_session(request: Request):
    """Create a research session + one bounded task carrying evidence URLs."""
    from drift.research import ResearchStore, _canonical_url
    brain = _get_brain(request)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="body must be valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    query = body.get("query", "")
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(status_code=400, detail="query must be a nonempty string")
    query = query.strip()
    if len(query) > 2000:
        raise HTTPException(status_code=400, detail="query too long")
    urls = body.get("urls", [])
    if not isinstance(urls, list) or len(urls) > 10:
        raise HTTPException(status_code=400, detail="urls must be a list of at most 10 URLs")
    try:
        for url in urls:
            if not isinstance(url, str) or len(url) > 1024:
                raise ValueError("URL must be a string of at most 1024 characters")
            _canonical_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    project_id = body.get("project_id")
    if project_id is not None:
        project_id = str(project_id)
        known = [p["id"] for p in brain.ledger.data.get("projects", [])]
        if project_id not in known:
            raise HTTPException(status_code=404, detail="project not found")
    store = ResearchStore(brain.env_path)
    evidence = "; ".join(urls) if urls else ""
    objective = f"Research: {query[:200]}"
    if evidence:
        objective += f" Evidence: {evidence[:500]}"
    # Create the bounded task first so the session checkpoint can carry
    # its identity via the public ResearchStore seam (no private access).
    task = brain.tasks.create_task(
        f"Research: {query[:80]}",
        objective,
        project_id=project_id,
        priority=0.5,
        estimated_cost=0.0,
    )
    try:
        session = store.start(query, task_id=task.id, project_id=project_id, urls=urls)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        brain.tasks.update_task(
            task.id,
            objective=f"Research session {session['id']}: {query[:200]}"
            + (f" Evidence: {evidence[:500]}" if evidence else ""),
        )
    except (KeyError, AttributeError, ValueError):
        pass
    session = store.get(session["id"]) or session
    return {"session_id": session["id"], "task_id": task.id, "session": session}


@router.get("/research/sessions/{session_id}")
async def get_research_session(session_id: str, request: Request):
    """Fetch one durable research session."""
    from drift.research import ResearchStore
    brain = _get_brain(request)
    store = ResearchStore(brain.env_path)
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="research session not found")
    return {"session": session}


@router.post("/research/sessions/{session_id}/resume")
async def resume_research_session(session_id: str, request: Request):
    """Owner-requested retry of the same bounded task, retaining its evidence."""
    from drift.research import ResearchStore
    brain = _get_brain(request)
    store = ResearchStore(brain.env_path)
    try:
        session = store.get(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid research session id")
    if session is None:
        raise HTTPException(status_code=404, detail="research session not found")
    recovering = session.get("state") == "researching" and session.get("repair_pending")
    if session.get("state") != "needs_review" and not recovering:
        raise HTTPException(status_code=409, detail="only needs_review or pending repair can resume")
    repair_budget = int(config.get("research_max_repairs", 1))
    if not recovering and int(session.get("owner_repair_attempts", 0)) >= repair_budget:
        raise HTTPException(409, "Research repair budget exhausted")
    task = brain.tasks.get_task(session.get("task_id", ""))
    if task is None:
        raise HTTPException(status_code=409, detail="original research task not found")
    if task.status == "complete":
        raise HTTPException(status_code=409, detail="completed task cannot resume")
    try:
        from drift.task import PHASES
        changes = {"status": "pending", "blockers": []}
        if task.phase == "blocked":
            if task._prev_phase not in PHASES or task._prev_phase == "complete":
                raise ValueError("original task has no valid resumable phase")
            changes["phase"] = task._prev_phase
        session = store.request_repair(session_id, max_attempts=repair_budget)
        brain.tasks.update_task(task.id, **changes)
        session = store.confirm_repair(session_id)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=409, detail=str(e))
    except OSError:
        raise HTTPException(status_code=503, detail="retry persistence failed; retry the same session to recover")
    return {"session_id": session_id, "task_id": task.id, "session": session}


@router.get("/decisions")
async def decision_telemetry(request: Request):
    """Bounded aggregate diagnostics; no raw memory or provider request state."""
    from drift.decisions import get_decision_summary
    brain = _get_brain(request)
    return {"loop": brain.decision_status(),
            "memory": get_decision_summary(brain.env_path)}


# ---------------------------------------------------------------------------
# Research / evidence view
# ---------------------------------------------------------------------------

@router.get("/research")
async def list_research(request: Request):
    """List research findings and evidence."""
    brain = _get_brain(request)
    findings = [
        e for e in brain.ledger.data.get("events", [])
        if e.get("kind") == "finding"
    ]
    return {
        "findings": findings[-50:],
        "count": len(findings),
    }


@router.get("/research/evidence")
async def list_evidence(request: Request):
    """List all evidence with provenance."""
    brain = _get_brain(request)
    evidence = []
    for e in brain.ledger.data.get("events", []):
        if e.get("evidence"):
            evidence.append({
                "summary": e.get("summary", ""),
                "evidence": e.get("evidence", []),
                "confidence": e.get("confidence", 0),
                "source": e.get("source", ""),
                "timestamp": e.get("timestamp", ""),
            })
    return {"evidence": evidence[-50:]}


# ---------------------------------------------------------------------------
# Attention / budget dashboard
# ---------------------------------------------------------------------------

@router.get("/budget")
async def get_budget(request: Request):
    """Get attention economy budget status."""
    from drift.runtime_status import budget_status
    return budget_status(_get_brain(request))


@router.get("/attention/candidates")
async def get_candidates(request: Request):
    """Get current attention candidates (for debugging)."""
    brain = _get_brain(request)
    if hasattr(brain, "attention"):
        candidates = brain.attention.generate_candidates(brain)
        return {
            "candidates": [
                {
                    "source": c.source,
                    "description": c.description,
                    "project_id": c.project_id,
                    "base_priority": c.base_priority,
                    "estimated_cost": c.estimated_cost,
                }
                for c in candidates
            ]
        }
    return {"candidates": []}


# ---------------------------------------------------------------------------
# Context receipts
# ---------------------------------------------------------------------------

@router.get("/receipts")
async def list_receipts(request: Request, limit: int = 50):
    """List context receipts for auditability."""
    brain = _get_brain(request)
    receipts = brain.receipts.list_receipts(limit=limit)
    return {
        "receipts": [
            {
                "task_id": r.task_id,
                "context_budget": r.context_budget,
                "estimated_tokens": r.estimated_tokens,
                "selected_memory_ids": r.selected_memory_ids,
                "evidence_ids": r.evidence_ids,
                "model_provider": r.model_provider,
                "estimated_cost": r.estimated_cost,
                "timestamp": r.timestamp,
            }
            for r in receipts
        ],
        "total_estimated_cost": brain.receipts.get_total_estimated_cost(),
    }


@router.get("/receipts/{task_id}")
async def get_task_receipts(task_id: str, request: Request):
    """Get receipts for a specific task."""
    brain = _get_brain(request)
    receipts = brain.receipts.get_receipts_for_task(task_id)
    return {
        "task_id": task_id,
        "receipts": [
            {
                "context_budget": r.context_budget,
                "estimated_tokens": r.estimated_tokens,
                "selected_memory_ids": r.selected_memory_ids,
                "model_provider": r.model_provider,
                "estimated_cost": r.estimated_cost,
                "timestamp": r.timestamp,
            }
            for r in receipts
        ],
    }


# ---------------------------------------------------------------------------
# Approval center
# ---------------------------------------------------------------------------

@router.get("/approvals")
async def list_approvals(request: Request):
    """List pending approvals (sensitive actions awaiting authorization)."""
    brain = _get_brain(request)
    # For now, return blocked tasks that need attention
    blocked = brain.tasks.list_tasks(status="blocked")
    return {
        "pending": [
            {
                "id": t.id,
                "goal": t.goal,
                "objective": t.objective,
                "project_id": t.project_id,
                "blockers": t.blockers,
                "phase": t.phase,
            }
            for t in blocked
        ]
    }


@router.post("/approvals/{task_id}/approve")
async def approve_task(task_id: str, request: Request):
    """Approve a blocked task to resume."""
    brain = _get_brain(request)
    task = brain.tasks.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Unblock the task
    from drift.task import can_transition
    if task.status == "blocked" and can_transition(task, task._prev_phase):
        brain.tasks.update_task(task.id, status="pending", phase=task._prev_phase,
            attempt_count=0, blockers=[])
        return {"ok": True, "task_id": task_id, "status": "pending"}
    raise HTTPException(status_code=400, detail="Cannot approve this task")


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications")
async def list_notifications(request: Request):
    """Get recent notifications (significant events)."""
    brain = _get_brain(request)
    # Use events as notifications
    events = brain.ledger.data.get("events", [])
    notifications = []
    for e in events[-20:]:
        notifications.append({
            "type": e.get("kind", "unknown"),
            "summary": e.get("summary", ""),
            "confidence": e.get("confidence", 0),
            "timestamp": e.get("timestamp", ""),
            "source": e.get("source", ""),
        })
    return {"notifications": notifications}


# ---------------------------------------------------------------------------
# Capabilities (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/capabilities")
async def list_capabilities(request: Request):
    """List available capabilities and their providers."""
    from drift.capabilities import list_capabilities, route_capability
    caps = list_capabilities()
    result = {}
    for name, desc in caps.items():
        try:
            provider = route_capability(name)
            result[name] = {
                "description": desc,
                "provider": provider.name,
                "model": provider.model,
                "cost_per_1k_tokens": provider.cost_per_1k_tokens,
            }
        except RuntimeError:
            result[name] = {
                "description": desc,
                "provider": "unavailable",
                "model": "none",
                "cost_per_1k_tokens": 0,
            }
    return {"capabilities": result}


# ---------------------------------------------------------------------------
# Health (Phase 6)
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check(request: Request):
    """System health check."""
    from drift.security import check_health
    brain = _get_brain(request)
    health = check_health(brain.env_path)
    return health.to_dict()


# ---------------------------------------------------------------------------
# Usage telemetry (Phase 4)
# ---------------------------------------------------------------------------

@router.get("/usage")
async def get_usage(request: Request):
    """Get model usage telemetry."""
    from drift.capabilities import USAGE
    return USAGE.summary()
