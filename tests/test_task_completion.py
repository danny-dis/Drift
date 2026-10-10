"""Owner inputs must finish with an artifact, not burn retries while idle."""
import asyncio
import json
from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.memory import MemoryStream
from drift.server import create_app
from drift.config import config


def ready(tmp_path):
    br = Brain({'name': 'owner'}, str(tmp_path))
    br.stream = MemoryStream(str(tmp_path)); br._init_stores()
    return br, TestClient(create_app({'owner': br}))


def test_captured_idea_produces_answer_and_no_repeat(tmp_path, monkeypatch):
    import drift.brain as module
    br, client = ready(tmp_path)
    assert client.post('/api/ui/projects', json={'name': 'pathlib filesystem', 'repo': ''}).status_code == 200
    response = client.post('/api/ui/ideas', json={'text': 'pathlib filesystem paths'})
    assert response.status_code == 200
    task = br.tasks.get_next_task(); calls = []
    monkeypatch.setattr(module, 'chat', lambda *a, **kw: calls.append(kw) or
        {'text': 'Proposal: use pathlib, subject to owner review.', 'tool_calls': [], 'output': []})
    asyncio.run(br._think_once())
    assert br.tasks.get_task(task.id).status == 'complete'
    answer = tmp_path / 'answers' / (task.id + '.md')
    assert answer.exists() and 'unverified' in answer.read_text(encoding='utf-8').lower()
    assert len(br.receipts.get_receipts_for_task(task.id)) == 1
    assert task.project_id == 'pathlib-filesystem'
    # Only check repeat processing of this idea (project monitoring is separate).
    from drift.attention import generate_candidates
    assert not [c for c in generate_candidates(br) if c.source == 'unqualified_idea']


def test_owner_message_creates_durable_task(tmp_path):
    br, client = ready(tmp_path)
    assert client.post('/api/message', json={'text': 'Explain this project safely'}).status_code == 200
    assert len(br.tasks.list_tasks()) == 1
    assert 'Explain this project safely' in br.tasks.get_next_task().objective


def test_owner_approval_resets_task_limit_not_global_budget(tmp_path, monkeypatch):
    br, client = ready(tmp_path)
    task = br.tasks.create_task('retry', 'retry')
    br.tasks.update_task(task.id, phase='blocked', status='blocked', attempt_count=4)
    from drift.providers import CallBudget
    CallBudget(str(tmp_path)).reserve()
    assert client.post(f'/api/ui/approvals/{task.id}/approve').status_code == 200
    assert br.tasks.get_task(task.id).attempt_count == 0
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 1


def test_empty_report_does_not_complete_research(tmp_path):
    from drift.research import ResearchStore
    store = ResearchStore(str(tmp_path)); session = store.start('Find something')
    store.add_source(session['id'], 'https://example.com', 'Something exists.')
    result = store.finish(session['id'], {'findings': [], 'citations': []})
    assert result['state'] == 'needs_review'


def test_optional_decisions_reserve_is_not_boolean(monkeypatch, tmp_path):
    import drift.decisions as module
    monkeypatch.setitem(config, 'free_only', False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'fixture-not-secret')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, *a): return json.dumps({'answers': {}, 'usage': {}}).encode()
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **kw: Response())
    assert module._request_decisions({}, str(tmp_path))['answers'] == {}
