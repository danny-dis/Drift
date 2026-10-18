"""Inspect internal advisory intelligence and publish only on owner confirmation."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from drift.organism import update_drift_md


router = APIRouter(prefix='/api/ui/projects', tags=['project-intelligence'])


def _project(request, project_id):
    brains = getattr(request.app.state, 'drift_brains', {})
    key = request.query_params.get('crab')
    if not brains:
        raise HTTPException(503, 'No Drift organisms running')
    if key and key not in brains:
        raise HTTPException(404, 'organism not found')
    brain = brains[key] if key else next(iter(brains.values()))
    project = next((p for p in brain.ledger.data['projects'] if p['id'] == project_id), None)
    if project is None:
        raise HTTPException(404, 'project not found')
    return project


@router.get('/{project_id}/intelligence')
def read_intelligence(project_id: str, request: Request):
    project = _project(request, project_id)
    return {'intelligence': project.get('intelligence'),
            'publish_available': bool(project.get('local_path'))}


@router.post('/{project_id}/intelligence/publish')
async def publish_intelligence(project_id: str, request: Request):
    project = _project(request, project_id)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, 'confirmation must be valid JSON')
    if not isinstance(body, dict) or body.get('confirm') is not True:
        raise HTTPException(400, 'explicit confirm: true is required')
    root = project.get('local_path')
    intelligence = project.get('intelligence')
    if not root or not Path(root).is_dir() or not intelligence:
        raise HTTPException(409, 'registered local project and internal intelligence are required')
    try:
        update_drift_md(root,
            state='Unverified advisory intelligence; owner review required. ' + intelligence.get('summary', ''),
            findings=intelligence.get('findings', []),
            challenges=intelligence.get('challenges', []),
            alternatives=intelligence.get('alternatives', []),
            questions=intelligence.get('questions', []),
            evidence=intelligence.get('report_paths', []))
    except (OSError, ValueError):
        raise HTTPException(409, 'Project document is unsafe or unavailable; inspect drift.md before retrying') from None
    return {'ok': True, 'path': str(Path(root) / 'drift.md'), 'verified': False}
