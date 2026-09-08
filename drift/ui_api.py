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
    brains = getattr(request.app.state, "drift_brains", {})
    if not brains:
        raise HTTPException(status_code=503, detail="No Drift organisms running")
    crab_id = request.query_params.get("crab")
    if crab_id and crab_id in brains:
        return brains[crab_id]
    return next(iter(brains.values()))


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
    """Create a new idea from text."""
    brain = _get_brain(request)
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    from drift.pipeline import IdeaPipeline
    pipeline = IdeaPipeline(brain.ledger, brain.tasks, {})
    idea = pipeline.capture_idea(text)
    return {"idea": {"id": idea.id, "text": idea.text, "concepts": idea.concepts, "status": idea.status}}


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
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"idea": {"id": idea.id, "status": idea.status}}


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
    brain = _get_brain(request)
    if hasattr(brain, "attention"):
        status = brain.attention.get_status()
    else:
        status = {}
    return status


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
        brain.tasks.update_task(task.id, status="pending", phase=task._prev_phase)
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
