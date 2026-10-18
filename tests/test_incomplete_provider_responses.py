"""Explicit provider truncation cannot become a completed advisory outcome."""
import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from drift import providers
from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.memory import MemoryStream


@pytest.fixture(autouse=True)
def offline_config(monkeypatch):
    for key, value in {'embeddings_enabled': False, 'llm_scoring_enabled': False,
                       'daily_max_model_calls': 40, 'weekly_max_model_calls': 200}.items():
        monkeypatch.setitem(config, key, value)


def completion(text, reason, calls=()):
    return NS(choices=[NS(finish_reason=reason, message=NS(content=text, tool_calls=[
        NS(id='call_one', function=NS(name='fixture_tool', arguments=args)) for args in calls]))])


def response_api(monkeypatch, text, status, details=None, calls=()):
    response = NS(status=status, incomplete_details=NS(reason=details) if details else None,
                  output=[NS(type='message', content=[NS(text=text)])] + [
                      NS(type='function_call', name='fixture_tool', call_id='call_one', arguments=args)
                      for args in calls], usage=None, model='fixture')
    client = NS(responses=NS(create=lambda **kwargs: response))
    monkeypatch.setattr(providers, '_client', lambda: nullcontext(client))
    return providers._chat_responses([], tools=False)


@pytest.mark.parametrize('reason', ['length', 'content_filter', 'provider_error'])
def test_completions_preserve_termination_metadata(reason):
    result = providers._normalize_completions_response(completion('Partial text', reason))
    assert result['text'] == 'Partial text'
    assert result['finish_reason'] == reason


def test_responses_api_preserves_incomplete_details(monkeypatch):
    result = response_api(monkeypatch, 'Partial text', 'incomplete', 'max_output_tokens')
    assert result['status'] == 'incomplete'
    assert result['incomplete_details'] == {'reason': 'max_output_tokens'}


@pytest.mark.parametrize('api,termination,details', [
    ('completions', 'length', None), ('completions', 'content_filter', None),
    ('responses', 'incomplete', 'max_output_tokens'), ('responses', 'failed', None),
    ('responses', 'cancelled', None), ('responses', 'in_progress', None),
    ('responses', 'completed', 'content_filter'),
])
@pytest.mark.parametrize('followup', [False, True])
def test_partial_answer_blocks_before_tools_and_survives_restart(tmp_path, monkeypatch, api, termination, details, followup):
    brain = Brain({'name': 'incomplete'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path)); brain._init_stores()
    capture = CaptureStore(str(tmp_path)).capture('Retain this synthetic original')['capture']
    text = '{"summary": "unfinished ' + ('retained text ' * 1100)
    if api == 'completions':
        partial = providers._normalize_completions_response(completion(text, termination, ['{}']))
    else:
        partial = response_api(monkeypatch, text, termination, details, ['{}'])
    # The runtime guard must also protect older adapters that retain tool calls.
    partial['tool_calls'] = [{'name': 'fixture_tool', 'arguments': {}, 'call_id': 'call_partial'}]
    responses = [providers._normalize_completions_response(completion('Tool prelude', 'tool_calls', ['{}'])), partial] if followup else [partial]
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        return responses.pop(0) if responses else {'text': 'WRONG final', 'tool_calls': [], 'output': []}
    tools = []
    monkeypatch.setattr('drift.brain.chat', model)
    monkeypatch.setattr('drift.brain.execute_tool', lambda *args: tools.append(args) or 'fixture result')
    async def emit_api_call(instructions, items, response):
        if response is partial:
            raise AssertionError('Incomplete output must be retained before optional event emission')
    monkeypatch.setattr(brain, '_emit_api_call', emit_api_call)
    asyncio.run(brain._think_once())
    task = brain.tasks.list_tasks()[0]
    assert task.phase == task.status == 'blocked'
    assert len(tools) == int(followup)
    assert len(calls) == 1 + int(followup)
    assert termination in task.blockers[0]
    artifact = Path(task.last_evidence)
    assert artifact.is_file()
    assert text in artifact.read_text(encoding='utf-8')
    assert not (tmp_path / 'answers' / (task.id + '.md')).exists()
    saved = CaptureStore(str(tmp_path)).get(capture['id'])
    assert saved['status'] == 'needs_review'
    assert saved['text'] == capture['text']
    idea = next(i for i in brain.ledger.data['ideas'] if i['id'] == task.idea_id)
    assert task.id not in idea.get('outcomes', {})
    restarted = Brain({'name': 'incomplete'}, str(tmp_path))
    restarted.stream = MemoryStream(str(tmp_path)); restarted._init_stores()
    monkeypatch.setattr(restarted, '_create_attention_task', lambda: None)
    asyncio.run(restarted._think_once())
    assert len(calls) == 1 + int(followup)
    assert restarted.tasks.get_task(task.id).status == 'blocked'


@pytest.mark.parametrize('api', ['completions', 'responses'])
def test_truncated_tool_arguments_do_not_discard_partial_text(monkeypatch, api):
    if api == 'completions':
        result = providers._normalize_completions_response(completion('Retained partial', 'length', ['{"unfinished":']))
    else:
        result = response_api(monkeypatch, 'Retained partial', 'incomplete', 'max_output_tokens', ['{"unfinished":'])
    assert result['text'] == 'Retained partial'
    assert result['tool_calls'] == []


@pytest.mark.parametrize('metadata', [{}, {'finish_reason': None}, {'finish_reason': 'stop'},
                                     {'status': 'completed', 'incomplete_details': None}])
def test_legacy_missing_metadata_and_explicit_success_still_complete(tmp_path, monkeypatch, metadata):
    brain = Brain({'name': 'complete'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path)); brain._init_stores()
    capture = CaptureStore(str(tmp_path)).capture('Synthetic legacy response')['capture']
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: {
        'text': 'An unverified but complete answer', 'tool_calls': [], 'output': [], **metadata})
    asyncio.run(brain._think_once())
    assert brain.tasks.list_tasks()[0].status == 'complete'
    assert CaptureStore(str(tmp_path)).get(capture['id'])['status'] == 'processed'


def test_owner_approved_retry_retains_both_incomplete_responses(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from drift.server import create_app
    monkeypatch.delenv('DRIFT_API_TOKEN', raising=False)
    brain = Brain({'name': 'retry'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    capture = CaptureStore(tmp_path).capture('Synthetic partial retry thought')['capture']
    responses = iter(['FIRST partial response', 'SECOND partial response'])
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: {
        'text': next(responses), 'tool_calls': [], 'output': [], 'finish_reason': 'length'})
    asyncio.run(brain._think_once())
    task = brain.tasks.list_tasks()[0]
    first = Path(task.last_evidence)
    client = TestClient(create_app({'retry': brain}))
    assert client.post(f'/api/ui/approvals/{task.id}/approve').status_code == 200
    asyncio.run(brain._think_once())
    second = Path(task.last_evidence)
    assert first != second
    assert 'FIRST partial response' in first.read_text(encoding='utf-8')
    assert 'SECOND partial response' in second.read_text(encoding='utf-8')
    assert task.status == 'blocked'
    assert CaptureStore(tmp_path).get(capture['id'])['text'] == 'Synthetic partial retry thought'
