"""Expose advisory outcomes separately from immutable captured originals."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from drift.capture_store import CaptureStore


router = APIRouter(prefix='/api/ui/captures', tags=['capture-insights'])


def _context(request, capture_id):
    brains = getattr(request.app.state, 'drift_brains', {})
    key = request.query_params.get('crab')
    if not brains:
        raise HTTPException(503, 'No Drift organisms running')
    if key and key not in brains:
        raise HTTPException(404, 'organism not found')
    brain = brains[key] if key else next(iter(brains.values()))
    capture = CaptureStore(brain.env_path).get(capture_id)
    if capture is None:
        raise HTTPException(404, 'capture not found')
    parts = sorted((t for t in brain.tasks.list_tasks(limit=100000)
                    if getattr(t, 'capture_id', '') == capture_id), key=lambda t: t.part_index)
    idea = next((i for i in brain.ledger.data['ideas'] if i['id'] == capture.get('idea_id')), {})
    outcomes = idea.get('outcomes', {})
    records = [outcomes[t.id] for t in parts if t.id in outcomes]
    return brain, capture, parts, records


@router.get('/{capture_id}/insights')
def read_insights(capture_id: str, request: Request):
    _, capture, parts, records = _context(request, capture_id)
    return {'capture_id': capture_id, 'status': capture['status'], 'verified': False,
            'summaries': [r['summary'] for r in records],
            'questions': list(dict.fromkeys(q for r in records for q in r.get('questions', []))),
            'qualification': records[-1]['qualification'] if records else None,
            'progress': {'complete': sum(t.status == 'complete' for t in parts),
                         'total': parts[0].part_count if parts else 0}}


@router.get('/{capture_id}/report')
def read_capture_report(capture_id: str, request: Request):
    brain, _, parts, _ = _context(request, capture_id)
    root = Path(brain.env_path).resolve()
    content = ['# Thought processing report', '', 'Unverified advisory output; original thought retained unchanged.', '']
    remaining = 30000
    included = 0
    for task in parts:
        if not task.last_evidence:
            continue
        path = Path(task.last_evidence).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            continue
        with path.open(encoding='utf-8') as stream:
            text = stream.read(remaining + 1)
        content.extend([f'## Part {task.part_index + 1}/{task.part_count}', text[:remaining], ''])
        included += 1
        remaining -= len(text)
        if remaining <= 0:
            break
    if not included:
        raise HTTPException(404, 'no processing report yet')
    return {'capture_id': capture_id, 'text': '\n'.join(content),
            'truncated': remaining <= 0, 'verified': False}
