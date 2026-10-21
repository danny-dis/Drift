import asyncio
import json

from drift.config import config
from drift.organism import Project
from drift.providers import CallBudget
from tests.test_capture_ux import ready


def test_explicit_wiki_queue_generates_source_linked_isolated_bounded_page(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Scoped project', 'owner/one'))
    brain.ledger.add_project(Project('two', 'UNRELATED_PROJECT_SECRET', 'owner/two'))
    idea = brain.ledger.add_idea('SCOPED_SOURCE evidence with uncertainty')
    other = brain.ledger.add_idea('UNRELATED_IDEA_SECRET')
    brain.ledger.mutate(lambda data: data['ideas'][0].update(related_projects=['one']))
    brain.stream.add('GLOBAL_MEMORY_SECRET', 'thought')
    brain._user_message = 'PENDING_MESSAGE_SECRET'
    brain._inbox_pending = [{'name': 'global', 'content': 'INBOX_SECRET'}]
    seen = []
    def provider(items, tools=True, instructions=None, max_tokens=300, **kwargs):
        seen.append((items, tools, instructions))
        return {'text': '# Generated\n\nSCOPED_SOURCE is tentative. [idea](' + idea.id + ')',
                'tool_calls': [], 'output': [], 'usage': {}}
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    monkeypatch.setitem(config, 'max_context_chars', 3000)
    monkeypatch.setitem(config, 'daily_max_model_calls', 2)
    assert client.get('/api/ui/wiki').status_code == 200
    assert seen == []
    assert client.post('/api/ui/wiki/generate', json={'title': 'Overview', 'project_id': 'one'}).status_code == 422
    response = client.post('/api/ui/wiki/generate', json={'title': 'Overview', 'project_id': 'one', 'confirm': True})
    assert response.status_code == 200, response.text
    page = response.json()['page']
    task_id = response.json()['task_id']
    assert page['status'] == 'queued' and page['text'] == ''
    assert seen == []
    assert brain.tasks.get_task(task_id).wiki_page_id == page['id']
    asyncio.run(brain._think_once())
    assert len(seen) == 1 and seen[0][1] is False
    payload = json.dumps(seen)
    assert 'SCOPED_SOURCE' in payload
    for marker in ('UNRELATED_PROJECT_SECRET', 'UNRELATED_IDEA_SECRET', 'GLOBAL_MEMORY_SECRET', 'PENDING_MESSAGE_SECRET', 'INBOX_SECRET'):
        assert marker not in payload
    assert len(json.dumps(seen[0][0], ensure_ascii=False)) + len(seen[0][2]) <= 3000
    finished = client.get('/api/ui/wiki/' + page['id']).json()['page']
    assert finished['status'] == 'complete' and finished['verified'] is False
    assert 'Generated' in finished['text']
    assert {s['id'] for s in finished['sources']} == {'one', idea.id}
    assert all('revision' in s for s in finished['sources'])
    assert brain.tasks.get_task(task_id).status == 'complete'
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 1
    assert len(brain.receipts.get_receipts_for_task(task_id)) == 1
    restarted, other_client = ready(tmp_path)
    assert other_client.get('/api/ui/wiki/' + page['id']).json()['page']['text'] == finished['text']
    assert other_client.patch('/api/ui/ideas/' + idea.id, json={'text': 'new evidence', 'expected_revision': 0}).status_code == 200
    assert other_client.get('/api/ui/wiki/' + page['id']).json()['page']['stale'] is True


def test_archiving_any_queued_wiki_source_suppresses_generation(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    idea = brain.ledger.add_idea('Source must be removable from queued global wiki')
    response = client.post('/api/ui/wiki/generate', json={'title': 'Global overview', 'confirm': True}).json()
    called = []
    monkeypatch.setattr('drift.providers._chat_completions', lambda *a, **k: called.append(1))
    assert client.request('DELETE', '/api/ui/ideas/' + idea.id, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert brain.tasks.get_next_task() is None
    assert client.get('/api/ui/wiki/' + response['page']['id']).json()['page']['status'] == 'blocked'
    assert called == []


def test_wiki_failure_retry_is_bounded_and_retains_sources(tmp_path, monkeypatch):
    import httpx
    import openai
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Only source', 'owner/one'))
    seen = []
    def provider(*a, **k):
        seen.append(1)
        raise openai.APITimeoutError(request=httpx.Request('POST', 'http://127.0.0.1'))
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    monkeypatch.setitem(config, 'max_provider_attempts', 2)
    monkeypatch.setitem(config, 'max_model_calls_per_task', 1)
    response = client.post('/api/ui/wiki/generate', json={'title': 'Retry', 'project_id': 'one', 'confirm': True}).json()
    asyncio.run(brain._think_once())
    page = client.get('/api/ui/wiki/' + response['page']['id']).json()['page']
    assert page['status'] == 'blocked' and page['text'] == ''
    assert page['sources'][0]['id'] == 'one'
    assert brain.tasks.get_task(response['task_id']).attempt_count == 1
    assert len(seen) == 1
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 1
    monkeypatch.setattr(brain, '_create_attention_task', lambda: None)
    asyncio.run(brain._think_once())
    assert len(seen) == 1


def test_wiki_closed_budget_and_invalid_fields_never_call_provider(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Source', ''))
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    calls = []
    monkeypatch.setattr('drift.providers._chat_completions', lambda *a, **k: calls.append(1))
    assert client.post('/api/ui/wiki/generate', json={'title': 'x', 'project_id': 'missing', 'confirm': True}).status_code == 404
    assert client.post('/api/ui/wiki/generate', json={'title': 'x', 'project_id': [], 'confirm': True}).status_code == 422
    assert client.post('/api/ui/wiki/generate', json={'title': 'x', 'confirm': True, 'tools': True}).status_code == 422
    response = client.post('/api/ui/wiki/generate', json={'title': 'x', 'confirm': True}).json()
    asyncio.run(brain._think_once())
    assert calls == []
    assert client.get('/api/ui/wiki/' + response['page']['id']).json()['page']['status'] == 'blocked'


def test_zero_daily_allowance_is_reported_blocked_at_queue_time(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Source', ''))
    monkeypatch.setitem(config, 'daily_max_model_calls', 0)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    calls = []
    monkeypatch.setattr('drift.providers._chat_completions', lambda *a, **k: calls.append(1))
    result = client.post('/api/ui/wiki/generate', json={'title': 'No allowance', 'confirm': True})
    assert result.status_code == 200
    queued = result.json()
    assert queued['page']['status'] == 'blocked'
    assert brain.tasks.get_task(queued['task_id']).status == 'blocked'
    asyncio.run(brain._think_once())
    assert calls == []
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0
    assert client.get('/api/ui/wiki/' + queued['page']['id']).json()['page']['status'] == 'blocked'


def test_wiki_context_discloses_source_omissions_and_neutralizes_html(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    for n in range(40):
        brain.ledger.add_idea(f'idea {n} ' + 'long source content ' * 300)
    monkeypatch.setitem(config, 'max_context_chars', 2200)
    def provider(*a, **k):
        return {'text': '<script>alert(1)</script> [click](javascript:alert) ![tracking](https://example.com/a)',
                'tool_calls': [], 'output': [], 'usage': {}}
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    response = client.post('/api/ui/wiki/generate', json={'title': 'Excerpts', 'confirm': True})
    assert response.status_code == 200, response.text
    page = response.json()['page']
    assert page['omitted_source_count'] > 0 and page['truncated_source_count'] > 0
    asyncio.run(brain._think_once())
    finished = client.get('/api/ui/wiki/' + page['id']).json()['page']
    assert finished['status'] == 'complete'
    assert '<script>' not in finished['text'] and 'javascript:' not in finished['text']
    assert 'https://' not in finished['text']


def test_wiki_incomplete_response_retains_partial_without_claiming_completion(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Evidence', ''))
    def provider(*a, **k):
        return {'text': 'partial advisory text', 'tool_calls': [], 'output': [],
                'finish_reason': 'length', 'usage': {}}
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    result = client.post('/api/ui/wiki/generate', json={'title': 'Partial', 'confirm': True}).json()
    asyncio.run(brain._think_once())
    page = client.get('/api/ui/wiki/' + result['page']['id']).json()['page']
    assert page['status'] == 'blocked' and page['text'] == ''
    assert page['partial_text'] == 'partial advisory text'
    assert page['verified'] is False
