"""Offline archive execution boundaries and queue-I/O regressions."""
import asyncio
import json
from pathlib import Path
import sqlite3
import time

import pytest

from drift.task import Task, TaskStore
from tests.test_capture_ux import ready


def test_staging_archive_restore_requires_explicit_task_approval(tmp_path, monkeypatch):
    import drift.intake as intake
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'race during staging'}).json()['capture']
    path = '/api/ui/captures/' + capture['id']
    original = intake._ensure_idea

    def interrupted(*args):
        assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': 0}).status_code == 200
        return original(*args)

    monkeypatch.setattr(intake, '_ensure_idea', interrupted)
    assert intake.stage_captures(brain) == 1
    task = brain.tasks.list_tasks()[0]
    assert task.archive_hold and task.status == 'blocked'
    assert client.post(path + '/restore', json={'confirm': True}).status_code == 200
    restarted, other = ready(tmp_path)
    assert restarted.tasks.get_next_task() is None
    assert other.post('/api/ui/approvals/' + task.id + '/approve').status_code == 200
    assert restarted.tasks.get_next_task().id == task.id
    again = TaskStore(str(tmp_path))
    assert again.get_next_task().id == task.id
    assert again.get_task(task.id).source_text == 'race during staging'


def test_selection_respects_source_hold_when_archive_sweep_never_ran(tmp_path):
    from drift.capture_store import CaptureStore
    brain, _ = ready(tmp_path)
    store = CaptureStore(tmp_path)
    capture = store.capture('crash before archive sweep')['capture']
    task = brain.tasks.create_task('Work', 'Preserve', capture_id=capture['id'])
    # Simulate process death after the durable source write, before sweeping tasks.
    store.revise(capture['id'], archived=True)
    store.revise(capture['id'], archived=False)
    assert not task.archive_hold
    assert TaskStore(str(tmp_path)).get_next_task() is None


def test_queue_selection_has_one_policy_snapshot(tmp_path, monkeypatch):
    from drift.capture_store import CaptureStore
    brain, _ = ready(tmp_path)
    capture = CaptureStore(tmp_path).capture('Retained thought')['capture']
    brain.ledger.mutate(lambda d: d['ideas'].extend(
        {'id': f'idea-{n:06}', 'text': 'x' * 1000} for n in range(500)))
    brain.tasks._tasks = {f'task-{n:06}': Task(id=f'task-{n:06}', goal='Queue load',
        objective='Read only', capture_id=capture['id']) for n in range(500)}
    original_read = Path.read_text
    original_connect = sqlite3.connect
    reads, queries = [], []

    def read(path, *args, **kwargs):
        if path.name == 'drift_ledger.json':
            reads.append(1)
        return original_read(path, *args, **kwargs)

    def connect(*args, **kwargs):
        db = original_connect(*args, **kwargs)
        db.set_trace_callback(lambda sql: queries.append(sql) if sql.lstrip().upper().startswith('SELECT') else None)
        return db

    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    start = time.perf_counter()
    assert brain.tasks.get_next_task().id == 'task-000000'
    seconds = time.perf_counter() - start
    print('PERF_SELECTION', {'pending_tasks': 500, 'ledger_bytes': brain.ledger.path.stat().st_size,
        'ledger_reads': len(reads), 'metadata_queries': len(queries), 'seconds': seconds})
    assert len(reads) <= 1
    assert len(queries) <= 1
    assert all('text' not in sql.lower() for sql in queries)


def test_research_preparation_stops_after_archive_during_first_fetch(tmp_path, monkeypatch):
    from drift.organism import Project
    from drift.research import ResearchStore
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Project', ''))
    response = client.post('/api/ui/research/sessions', json={'query': 'bounded research',
        'project_id': 'one', 'urls': ['https://example.com/one', 'https://example.com/two']})
    assert response.status_code == 200, response.text
    seen = []

    def tool(name, args, root):
        seen.append(args['url'])
        if len(seen) == 1:
            assert client.request('DELETE', '/api/ui/projects/one',
                json={'confirm': True, 'expected_revision': 0}).status_code == 200
        return 'DISCARDED_FETCH_SENTINEL'

    monkeypatch.setattr('drift.brain.execute_tool', tool)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: pytest.fail('No model call after archive'))
    asyncio.run(brain._think_once())
    assert seen == ['https://example.com/one']
    assert 'DISCARDED_FETCH_SENTINEL' not in json.dumps(ResearchStore(tmp_path).list())
    assert all(not s['sources'] for s in ResearchStore(tmp_path).list())
    assert brain.state == 'idle'


@pytest.mark.parametrize('incomplete', [False, True])
@pytest.mark.parametrize('tool_name', ['read_file', 'fetch_url'])
def test_archived_followup_is_never_published(tmp_path, monkeypatch, incomplete, tool_name):
    brain, client = ready(tmp_path)
    idea = brain.ledger.add_idea('No publication after removal')
    task = brain.tasks.create_task('Work', 'Understand', idea_id=idea.id)
    calls, emitted = [], []

    def chat(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            return {'text': '', 'output': [], 'tool_calls': [
                {'name': tool_name, 'arguments': {'path': 'one', 'url': 'https://example.com/one'}, 'call_id': 'one'}]}
        assert client.request('DELETE', '/api/ui/ideas/' + idea.id,
            json={'confirm': True, 'expected_revision': 0}).status_code == 200
        response = {'text': 'DISCARDED_RESPONSE_SENTINEL', 'tool_calls': [], 'output': []}
        if incomplete:
            response['finish_reason'] = 'length'
        return response

    async def broadcast(message):
        emitted.append(message)

    monkeypatch.setattr('drift.brain.chat', chat)
    monkeypatch.setattr('drift.brain.execute_tool', lambda *a, **k: 'Offline tool output')
    monkeypatch.setattr(brain, '_broadcast', broadcast)
    asyncio.run(brain._think_once())
    assert len(calls) == 2
    assert task.status == 'blocked'
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(brain.stream.get_recent(n=20))
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(emitted)
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(brain.api_calls)
    assert not list((tmp_path / 'answers').glob('*.md'))
    assert not brain.ledger.data['ideas'][0].get('outcomes')
    from drift.research import ResearchStore
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(ResearchStore(tmp_path).list())
    assert brain.state == 'idle'


def test_old_explicit_approval_does_not_authorize_a_later_archive(tmp_path):
    from drift.capture_store import CaptureStore
    brain, _ = ready(tmp_path)
    store = CaptureStore(tmp_path)
    capture = store.capture('approval applies to one source generation')['capture']
    task = brain.tasks.create_task('Confirmed new request', 'Read restored source',
        capture_id=capture['id'], processing_approved=True)
    assert brain.tasks.get_next_task() is task
    # Another archive/restore, with no opportunity to sweep old approved tasks.
    store.revise(capture['id'], archived=True)
    store.revise(capture['id'], archived=False)
    assert TaskStore(str(tmp_path)).get_next_task() is None


def test_approval_is_task_local_and_never_stages_missing_siblings(tmp_path):
    from drift.intake import stage_captures
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'part ' * 1000}).json()['capture']
    assert stage_captures(brain, max_tasks=2) == 2
    tasks = brain.tasks.list_tasks()
    path = '/api/ui/captures/' + capture['id']
    assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert client.post(path + '/restore', json={'confirm': True}).status_code == 200
    assert client.post('/api/ui/approvals/' + tasks[0].id + '/approve').status_code == 200
    assert brain.tasks.get_next_task() is tasks[0]
    assert tasks[1].archive_hold and not tasks[1].processing_approved
    assert stage_captures(brain, max_tasks=20) == 0
    assert len(brain.tasks.list_tasks()) == 2


@pytest.mark.parametrize('checkpoint', ['ledger', 'capture'])
def test_corrupt_policy_checkpoint_fails_closed(tmp_path, checkpoint):
    from drift.capture_store import CaptureStore
    brain, _ = ready(tmp_path)
    capture = CaptureStore(tmp_path).capture('Original retained')['capture']
    task = brain.tasks.create_task('Work', 'Read', capture_id=capture['id'])
    if checkpoint == 'ledger':
        brain.ledger.path.write_text('{broken', encoding='utf-8')
    else:
        (tmp_path / 'captures.sqlite3').write_bytes(b'not a sqlite database')
    assert brain.tasks.get_next_task() is None
    assert task.archive_hold and task.status == 'blocked'


def test_batched_hold_sweep_preserves_task_parts_and_writes_once(tmp_path, monkeypatch):
    from drift.archive_policy import hold_archived_tasks
    from drift.capture_store import CaptureStore
    brain, _ = ready(tmp_path)
    brain.ledger.add_idea('Persist a ledger for the one-read sweep assertion')
    store = CaptureStore(tmp_path)
    capture = store.capture('x' * 1_000_000)['capture']
    brain.tasks._tasks = {f'task-{n:06}': Task(id=f'task-{n:06}', goal='Queue load',
        objective='Keep parts', capture_id=capture['id'], part_index=n, part_count=500,
        source_text=f'original part {n}', phase='research', attempt_count=2) for n in range(500)}
    store.revise(capture['id'], archived=True)
    original_read, original_connect, original_save = Path.read_text, sqlite3.connect, brain.tasks.save
    reads, queries, writes = [], [], []

    def read(path, *args, **kwargs):
        if path.name == 'drift_ledger.json':
            reads.append(1)
        return original_read(path, *args, **kwargs)

    def connect(*args, **kwargs):
        db = original_connect(*args, **kwargs)
        db.set_trace_callback(lambda sql: queries.append(sql) if sql.lstrip().upper().startswith('SELECT') else None)
        return db

    def save(*args, **kwargs):
        writes.append(1)
        return original_save(*args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    monkeypatch.setattr(brain.tasks, 'save', save)
    hold_archived_tasks(brain)
    assert len(reads) == len(queries) == len(writes) == 1
    assert all('text' not in sql.lower() for sql in queries)
    restarted = TaskStore(str(tmp_path))
    assert len(restarted._tasks) == 500
    for index in range(500):
        task = restarted.get_task(f'task-{index:06}')
        assert task.archive_hold and task.status == task.phase == 'blocked'
        assert task._prev_phase == 'research' and task.attempt_count == 2
        assert task.source_text == f'original part {index}'
        assert task.part_index == index and task.part_count == 500


def test_legacy_task_defaults_preserve_source_metadata():
    task = Task.from_dict({'id': 'task-000001', 'goal': 'Old', 'objective': 'Keep',
        'capture_id': 'capture', 'idea_id': 'idea', 'source_text': 'original',
        'part_index': 2, 'part_count': 4, 'attempt_count': 3})
    assert not task.processing_approved and task.processing_approval == {}
    assert not task.archive_hold
    assert task.capture_id == 'capture' and task.idea_id == 'idea'
    assert task.source_text == 'original' and task.part_index == 2 and task.part_count == 4
    assert task.attempt_count == 3
