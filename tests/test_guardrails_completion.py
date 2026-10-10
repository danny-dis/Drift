"""Controller regressions for the final runtime boundary, no network calls."""
import asyncio
import inspect
import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from drift import providers
from drift.brain import Brain, repack_context
from drift.config import config
from drift.server import create_app


def brain(tmp_path):
    br = Brain({'name': 'guard'}, str(tmp_path))
    br._init_stores()
    return br, TestClient(create_app({'guard': br}))


def test_foreign_origin_cannot_read_local_api(tmp_path):
    br, client = brain(tmp_path)
    assert client.get('/api/status', headers={'Origin': 'https://evil.example'}).status_code == 403


def test_foreign_host_cannot_rebind_local_api(tmp_path):
    br, client = brain(tmp_path)
    assert client.get('/api/status', headers={'Host': 'evil.example'}).status_code == 400


def test_token_protects_api_but_not_token_entry_page(tmp_path, monkeypatch):
    br, client = brain(tmp_path)
    # Test the real auth middleware against a public page fixture, not a
    # developer's ignored frontend build. Python CI runs without npm artifacts.
    from fastapi.responses import HTMLResponse
    from fastapi.routing import APIRoute
    public_page = APIRoute('/', lambda: HTMLResponse('<html>Token entry</html>'), methods=['GET'])
    monkeypatch.setattr(client.app.router, 'routes', [public_page, *client.app.router.routes])
    monkeypatch.setenv('DRIFT_API_TOKEN', 'fixture-only')
    assert client.get('/').status_code == 200
    assert client.get('/api/status').status_code == 401


def test_websocket_requires_configured_token(tmp_path, monkeypatch):
    br, client = brain(tmp_path)
    monkeypatch.setenv('DRIFT_API_TOKEN', 'fixture-only')
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws/guard'):
            pass


def test_free_only_blocks_paid_provider_before_request(tmp_path, monkeypatch):
    monkeypatch.setitem(config, 'provider', 'openai')
    monkeypatch.setitem(config, 'free_only', True)
    monkeypatch.setitem(config, 'environment_path', str(tmp_path))
    contacted = []
    monkeypatch.setattr(providers, '_chat_responses', lambda *args, **kw: contacted.append(1) or {'text': 'bad'})
    with pytest.raises(RuntimeError, match='free.only'):
        providers.chat([{'role': 'user', 'content': 'hello'}])
    assert not contacted


def test_chat_uses_organism_budget_and_actual_usage(tmp_path, monkeypatch):
    assert 'budget_root' in inspect.signature(providers.chat).parameters
    monkeypatch.setitem(config, 'provider', 'dmrx')
    monkeypatch.setitem(config, 'base_url', 'http://127.0.0.1:47113/v1')
    monkeypatch.setattr(providers, '_chat_completions', lambda *a, **kw: {
        'text': 'ok', 'output': [], 'tool_calls': [],
        'usage': {'prompt_tokens': 2, 'completion_tokens': 3}})
    providers.chat([{'role': 'user', 'content': 'hello'}], budget_root=str(tmp_path))
    assert providers.CallBudget(str(tmp_path)).status()['daily_tokens'] == 5


def test_repack_hard_bound_and_complete_pairs():
    history = [{'role': 'user', 'content': 'p' * 4000}]
    for i in range(5):
        history += [{'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': f'c{i}', 'type': 'function', 'function': {'name': 'fetch_url', 'arguments': '{}'}}]},
            {'type': 'function_call_output', 'call_id': f'c{i}', 'output': 'x' * 2000}]
    out = repack_context(history, 1800)
    assert len(json.dumps(out, ensure_ascii=False)) <= 1800
    calls = {tc['id'] for item in out for tc in item.get('tool_calls', [])}
    results = {item['call_id'] for item in out if item.get('type') == 'function_call_output'}
    assert calls == results


def test_created_file_advances_one_legal_phase(tmp_path):
    br = Brain({'name': 'guard'}, str(tmp_path))
    br._init_stores()
    task = br.tasks.create_task('idea', 'understand this idea')
    br._advance_task(task, {'note.md'})
    assert br.tasks.get_task(task.id).phase == 'understand'


def test_initial_model_call_bounds_owner_input_and_instructions(tmp_path, monkeypatch):
    import drift.brain as module
    br = Brain({'name': 'guard'}, str(tmp_path))
    br._init_stores()
    task = br.tasks.create_task('idea', 'understand')
    monkeypatch.setitem(config, 'max_context_chars', 1800)
    captured = []
    def fake_chat(items, tools=True, instructions=None, max_tokens=300, **kw):
        captured.append((items, instructions or ''))
        return {'text': 'ok', 'tool_calls': [], 'output': []}
    monkeypatch.setattr(module, 'chat', fake_chat)
    asyncio.run(br._invoke_model(task, [{'role': 'user', 'content': 'x' * 10000}], 's' * 10000))
    items, instructions = captured[0]
    assert len(json.dumps(items, ensure_ascii=False)) + len(instructions) <= 1800


def test_non_string_idea_rejected_without_task(tmp_path):
    br, client = brain(tmp_path)
    n = len(br.tasks.list_tasks())
    assert client.post('/api/ui/ideas', json={'text': {'not': 'an idea'}}).status_code == 400
    assert len(br.tasks.list_tasks()) == n
