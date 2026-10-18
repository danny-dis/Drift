"""Validate advisory answers and project them into durable domain state."""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from drift.organism import DriftEvent


OUTCOME_INSTRUCTIONS = (
    'Return a JSON object with summary (string), qualification '
    '(PROJECT, RESEARCH or PARKED), concepts (strings), findings (strings), '
    'challenges (strings), alternatives (strings), and questions (strings). '
    'Treat qualification as an advisory suggestion, never an instruction to '
    'create a repository. Do not invent evidence or label speculation verified. '
    'Preserve unresolved thoughts; parking is reversible and never deletion.'
)


def parse_outcome(text: str) -> dict[str, Any]:
    cleaned = text.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try:
        raw = json.loads(cleaned)
    except ValueError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    summary = raw.get('summary')
    if not isinstance(summary, str) or not summary.strip():
        summary = text[:1600]
    result = {'summary': summary[:1600], 'verified': False}
    for key in ('concepts', 'findings', 'challenges', 'alternatives', 'questions'):
        values = raw.get(key, [])
        result[key] = [s[:400] for s in values[:20] if isinstance(s, str) and s.strip()] if isinstance(values, list) else []
    qualification = raw.get('qualification')
    result['qualification'] = qualification if qualification in ('PROJECT', 'RESEARCH', 'PARKED') else 'RESEARCH'
    return result


def task_idea_id(task) -> str:
    explicit = getattr(task, 'idea_id', '')
    if explicit:
        return explicit
    match = re.search(r'\bidea-\d+\b', task.goal + ' ' + task.objective)
    return match.group(0) if match else ''


def _merge_strings(records: list[dict], key: str) -> list[str]:
    values = []
    for record in records:
        for value in record.get(key, []):
            if value not in values:
                values.append(value)
    return values[-30:]


def record_answer(brain, task, text: str, report_path: str) -> None:
    outcome = parse_outcome(text)
    outcome['report_path'] = report_path
    outcome['task_id'] = task.id
    outcome['updated_at'] = datetime.now(timezone.utc).isoformat()
    idea_id = task_idea_id(task)
    capture_id = getattr(task, 'capture_id', '')
    siblings = [t for t in brain.tasks.list_tasks(limit=100000)
                if capture_id and getattr(t, 'capture_id', '') == capture_id]
    finished = sum(t.id == task.id or t.status == 'complete' for t in siblings)
    all_finished = not capture_id or finished >= getattr(task, 'part_count', 1)

    def apply(data):
        idea = next((i for i in data['ideas'] if i['id'] == idea_id), None)
        if idea is not None:
            records = idea.setdefault('outcomes', {})
            records[task.id] = outcome
            idea.update(summary=outcome['summary'], last_evidence=report_path,
                        verified=False, status=outcome['qualification'] if all_finished else 'processing',
                        qualification_source='advisory outcome; owner may revise',
                        completed_parts=finished if siblings else 1,
                        total_parts=len(siblings) if siblings else 1)
            idea['concepts'] = list(dict.fromkeys(idea.get('concepts', []) + outcome['concepts']))
        project = next((p for p in data['projects'] if p['id'] == task.project_id), None)
        if project is not None:
            intelligence = project.setdefault('intelligence', {'tasks': {}})
            intelligence.setdefault('tasks', {})[task.id] = outcome
            records = list(intelligence['tasks'].values())[-30:]
            intelligence.update(summary=outcome['summary'], verified=False,
                                updated_at=outcome['updated_at'],
                                report_paths=[r['report_path'] for r in records])
            for key in ('findings', 'challenges', 'alternatives', 'questions'):
                intelligence[key] = _merge_strings(records, key)
            if not intelligence['findings']:
                intelligence['findings'] = [outcome['summary']]
        source = f'outcome:{task.id}'
        if not any(e.get('source') == source for e in data['events']):
            data['events'].append(asdict(DriftEvent(
                kind='finding', source=source, summary=outcome['summary'], confidence=0.0,
                evidence=[report_path], related_projects=[task.project_id] if project else [],
                related_ideas=[idea_id] if idea else [])))

    brain.ledger.mutate(apply)


def finish_capture_task(brain, task):
    capture_id = getattr(task, 'capture_id', '')
    if not capture_id:
        return
    parts = [t for t in brain.tasks.list_tasks(limit=100000) if getattr(t, 'capture_id', '') == capture_id]
    if len(parts) < task.part_count or any(t.status != 'complete' for t in parts):
        return
    from drift.capture_store import CaptureStore
    store = CaptureStore(brain.env_path)
    capture = store.get(capture_id)
    if capture and capture.get('task_id'):
        store.finish(capture['task_id'], 'processed', task.last_evidence)


def reconcile_capture_task(brain, task) -> None:
    """Project durable sibling task states; safe to repeat after interruption."""
    capture_id = getattr(task, 'capture_id', '')
    if not capture_id:
        return
    parts = [t for t in brain.tasks.list_tasks(limit=100000)
             if getattr(t, 'capture_id', '') == capture_id]
    if not parts:
        return
    from drift.capture_store import CaptureStore
    store = CaptureStore(brain.env_path)
    capture = store.get(capture_id)
    if not capture or not capture.get('task_id'):
        return
    if len(parts) >= task.part_count and all(t.status == 'complete' for t in parts):
        if capture['status'] != 'processed':
            finish_capture_task(brain, max(parts, key=lambda t: t.part_index))
        return
    status = 'needs_review' if any(t.status == 'blocked' for t in parts) else 'queued'
    if capture['status'] != status:
        store.set_status(capture_id, status)


def mark_capture_review(brain, task) -> None:
    if getattr(task, 'capture_id', ''):
        from drift.capture_store import CaptureStore
        store = CaptureStore(brain.env_path)
        capture = store.get(task.capture_id)
        if capture and capture.get('task_id'):
            store.finish(capture['task_id'], 'needs_review', task.last_evidence)


def block_task(brain, task, reason):
    changes = {'status': 'blocked', 'blockers': [reason]}
    if task.phase != 'blocked':
        changes['phase'] = 'blocked'
    brain.tasks.update_task(task.id, **changes)
    mark_capture_review(brain, task)
