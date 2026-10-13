import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.memory import MemoryStream
from drift.server import create_app


def ready(root):
    brain = Brain({'name': 'capture'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain, TestClient(create_app({'capture': brain}))


def answer(*args, **kwargs):
    return {'text': json.dumps({'summary': 'A retained part for later investigation.',
                                'qualification': 'RESEARCH'}), 'tool_calls': [], 'output': []}


def test_capture_is_saved_even_when_model_budget_is_closed(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    text = '  unfinished typos yhoughts\n\n' + 'ideas ' * 1000
    result = client.post('/api/ui/captures', json={'text': text, 'client_id': 'retry'})
    assert result.status_code == 200
    assert result.json()['capture']['text'] == text
    assert len(brain.tasks.list_tasks()) == 0
    asyncio.run(brain._think_once())
    store = CaptureStore(str(tmp_path))
    assert store.get(result.json()['capture']['id'])['text'] == text
    assert store.get(result.json()['capture']['id'])['status'] == 'queued'
    assert brain.tasks.get_next_task() is not None


def test_long_dump_is_partitioned_without_losing_or_reprocessing_parts(tmp_path, monkeypatch):
    import drift.brain as module
    brain, client = ready(tmp_path)
    text = 'start ' + ('some messy thoughts\n' * 650) + ' FINAL IMPORTANT THOUGHT '
    result = client.post('/api/ui/captures', json={'text': text, 'client_id': 'long'})
    assert result.status_code == 200
    capture_id = result.json()['capture']['id']
    monkeypatch.setattr(module, 'chat', answer)
    asyncio.run(brain._think_once())
    tasks = sorted([t for t in brain.tasks.list_tasks(limit=1000) if t.capture_id == capture_id], key=lambda t: t.part_index)
    assert len(tasks) > 1
    assert ''.join(t.source_text for t in tasks) == text
    assert CaptureStore(str(tmp_path)).get(capture_id)['status'] == 'queued'
    for _ in range(len(tasks) - 1):
        asyncio.run(brain._think_once())
    capture = CaptureStore(str(tmp_path)).get(capture_id)
    assert capture['status'] == 'processed'
    assert capture['text'] == text
    assert all(t.status == 'complete' for t in tasks)
    count = len(tasks)
    restarted, _ = ready(tmp_path)
    from drift.intake import stage_captures
    stage_captures(restarted)
    assert len(restarted.tasks.list_tasks(limit=1000)) == count


def test_partial_intake_recovers_missing_parts_without_duplicate_tasks(tmp_path):
    brain, _ = ready(tmp_path)
    store = CaptureStore(str(tmp_path))
    capture = store.capture('thought ' * 2000)['capture']
    from drift.intake import stage_captures
    stage_captures(brain, max_tasks=2)
    assert len(brain.tasks.list_tasks(limit=1000)) == 2
    restarted, _ = ready(tmp_path)
    stage_captures(restarted, max_tasks=30)
    tasks = [t for t in restarted.tasks.list_tasks(limit=1000) if t.capture_id == capture['id']]
    assert len(tasks) == tasks[0].part_count
    assert len({t.part_index for t in tasks}) == len(tasks)
    assert CaptureStore(str(tmp_path)).get(capture['id'])['status'] == 'queued'


def test_capture_database_is_not_treated_as_an_inbox_document(tmp_path):
    brain, _ = ready(tmp_path)
    CaptureStore(str(tmp_path)).capture('A new thought')
    incoming = brain._check_new_files()
    assert not [f for f in incoming if f['name'].startswith('captures.sqlite3')]
