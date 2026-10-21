import asyncio

from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.memory import MemoryStream
from drift.server import create_app


def ready(root):
    brain = Brain({'name': 'ux'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain, TestClient(create_app({'ux': brain}))


def test_edit_archive_restore_preserves_original_and_pagination(tmp_path):
    brain, client = ready(tmp_path)
    raw = '  Original unpolished thought\n'
    capture = client.post('/api/ui/captures', json={'text': raw, 'client_id': 'same'}).json()['capture']
    cid = capture['id']
    path = '/api/ui/captures/' + cid
    edited = client.patch(path, json={'text': 'Edited derivative', 'expected_revision': 0})
    assert edited.status_code == 200, edited.text
    assert edited.json()['capture']['text'] == raw
    assert edited.json()['capture']['current_text'] == 'Edited derivative'
    assert edited.json()['capture']['revision'] == 1
    assert client.patch(path, json={'text': 'stale', 'expected_revision': 0}).status_code == 409
    assert client.patch(path, json={'text': '', 'expected_revision': 1}).status_code == 422
    assert client.request('DELETE', path, json={'expected_revision': 1}).status_code == 422
    archived = client.request('DELETE', path, json={'confirm': True, 'expected_revision': 1})
    assert archived.status_code == 200, archived.text
    assert archived.json()['capture']['archived'] is True
    assert client.get('/api/ui/captures').json() == {'captures': [], 'total': 0, 'has_more': False}
    assert client.get('/api/ui/captures?include_archived=true&limit=1').json()['total'] == 1
    assert CaptureStore(tmp_path).pending() == []
    restarted, other = ready(tmp_path)
    assert other.get(path).json()['capture']['current_text'] == 'Edited derivative'
    assert other.post('/api/ui/captures', json={'text': raw, 'client_id': 'same'}).json()['deduplicated']
    restored = other.post(path + '/restore', json={'confirm': True})
    assert restored.status_code == 200, restored.text
    assert not restored.json()['capture']['archived']
    assert restored.json()['capture']['revision'] == 3
    assert len(restarted.tasks.list_tasks()) == 0
    assert other.patch('/api/ui/captures/unknown', json={'text': 'x', 'expected_revision': 0}).status_code == 404


def test_capture_search_finds_editable_derivative(tmp_path):
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Original'}).json()['capture']
    assert client.patch('/api/ui/captures/' + capture['id'], json={'text': 'New searchable derivative', 'expected_revision': 0}).status_code == 200
    assert client.get('/api/ui/captures?q=searchable').json()['total'] == 1


def test_archive_suppresses_multipart_staging_selection_and_approval(tmp_path):
    from drift.intake import stage_captures
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'multipart ' * 700}).json()['capture']
    stage_captures(brain, max_tasks=1)
    task = brain.tasks.list_tasks()[0]
    original_part = task.source_text
    path = '/api/ui/captures/' + capture['id']
    assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert brain.tasks.get_next_task() is None
    assert stage_captures(brain, max_tasks=20) == 0
    assert len(brain.tasks.list_tasks(limit=1000)) == 1
    assert client.post('/api/ui/approvals/' + task.id + '/approve').status_code == 409
    restarted, other = ready(tmp_path)
    assert restarted.tasks.get_next_task() is None
    assert other.post(path + '/restore', json={'confirm': True}).status_code == 200
    assert restarted.tasks.get_next_task() is None
    assert restarted.tasks.get_task(task.id).source_text == original_part


def test_archiving_during_provider_call_discards_completion(tmp_path, monkeypatch):
    from drift.intake import stage_captures
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'private thought'}).json()['capture']
    stage_captures(brain)
    task = brain.tasks.list_tasks()[0]
    def chat(*args, **kwargs):
        assert client.request('DELETE', '/api/ui/captures/' + capture['id'],
                              json={'confirm': True, 'expected_revision': 0}).status_code == 200
        return {'text': 'must not become an outcome', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', chat)
    asyncio.run(brain._think_once())
    assert task.status == 'blocked'
    assert not list((tmp_path / 'answers').glob('*.md'))
    assert 'outcomes' not in brain.ledger.data['ideas'][0]


def test_archive_during_transient_failure_cannot_spend_retry(tmp_path, monkeypatch):
    import httpx
    import openai
    from drift.config import config
    from drift.intake import stage_captures
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Stop even a transient retry'}).json()['capture']
    stage_captures(brain)
    seen = []
    def provider(*args, **kwargs):
        seen.append(1)
        if len(seen) == 1:
            client.request('DELETE', '/api/ui/captures/' + capture['id'], json={'confirm': True, 'expected_revision': 0})
            raise openai.APITimeoutError(request=httpx.Request('POST', 'http://127.0.0.1'))
        return {'text': 'must not retry', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    monkeypatch.setitem(config, 'max_provider_attempts', 2)
    asyncio.run(brain._think_once())
    assert seen == [1]


def test_restore_of_partially_completed_capture_never_stages_missing_parts(tmp_path):
    from drift.intake import stage_captures
    from drift.task import PHASES
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'long multipart ' * 500}).json()['capture']
    stage_captures(brain, max_tasks=1)
    task = brain.tasks.list_tasks()[0]
    for phase in PHASES[1:PHASES.index('complete') + 1]:
        brain.tasks.update_task(task.id, phase=phase, status='complete' if phase == 'complete' else 'pending')
    path = '/api/ui/captures/' + capture['id']
    assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert client.post(path + '/restore', json={'confirm': True}).status_code == 200
    assert stage_captures(brain, max_tasks=20) == 0
