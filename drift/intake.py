"""Bounded, restart-recoverable bridge from raw captures to thinking tasks."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from drift.capture_store import CaptureStore
from drift.organism import Idea
from drift.pipeline import IdeaPipeline
from drift.privacy import redact_slice


CHUNK_CHARS = 1200


def _ensure_idea(brain, capture):
    idea_id = 'thought-' + capture['id']
    projection = redact_slice(capture['text'], 0, 4000)
    def add(data):
        existing = next((i for i in data['ideas'] if i['id'] == idea_id), None)
        if existing is not None:
            return
        # The canonical original is immutable in CaptureStore, not this projection.
        idea = asdict(Idea(idea_id, projection,
                           concepts=IdeaPipeline(brain.ledger, brain.tasks, {}).extract_concepts(projection)))
        idea.update(capture_id=capture['id'], original_chars=len(capture['text']))
        data['ideas'].append(idea)
        data['mind_map']['nodes'].append({'id': idea_id, 'kind': 'idea', 'label': redact_slice(capture['text'], 0, 120)})
    brain.ledger.mutate(add)
    IdeaPipeline(brain.ledger, brain.tasks, {}).match_project(idea_id)
    return idea_id


def stage_captures(brain, limit=8, max_tasks=20):
    if not (Path(brain.env_path) / 'captures.sqlite3').exists():
        return 0
    store = CaptureStore(brain.env_path)
    tasks = brain.tasks.list_tasks(limit=100000)
    incomplete = {}
    for task in tasks:
        if getattr(task, 'capture_id', ''):
            incomplete.setdefault(task.capture_id, []).append(task)
    new = store.pending(limit=limit)
    captures = {c['id']: c for c in new}
    for capture_id, parts in incomplete.items():
        if len(parts) < parts[0].part_count:
            capture = store.get(capture_id)
            if capture:
                captures.setdefault(capture_id, capture)
    created = 0
    for capture in captures.values():
        from drift.archive_policy import capture_suppressed
        if capture_suppressed(brain, capture):
            continue
        if created >= max_tasks:
            break
        idea_id = _ensure_idea(brain, capture)
        text = capture['text']
        count = max(1, (len(text) + CHUNK_CHARS - 1) // CHUNK_CHARS)
        idea = next(i for i in brain.ledger.data['ideas'] if i['id'] == idea_id)
        links = idea.get('related_projects', [])
        parts = {t.part_index: t for t in tasks if getattr(t, 'capture_id', '') == capture['id']}
        for index in range(count):
            if index in parts:
                continue
            if created >= max_tasks:
                break
            task = brain.tasks.create_task(
                goal=f"Understand captured thought {capture['id']} part {index + 1}/{count}",
                objective='Organize this original thought part without discarding it. Keep uncertainty and open questions.',
                project_id=links[0] if links else None, priority=0.65,
                idea_id=idea_id, capture_id=capture['id'],
                part_index=index, part_count=count,
                source_text=text[index * CHUNK_CHARS:(index + 1) * CHUNK_CHARS])
            tasks.append(task)
            parts[index] = task
            created += 1
        if 0 in parts and not capture.get('task_id'):
            store.link(capture['id'], idea_id, parts[0].id)
    # Repair projections after interrupted completion or owner approval.
    from drift.outcomes import reconcile_capture_task
    for parts in incomplete.values():
        reconcile_capture_task(brain, parts[0])
    return created
