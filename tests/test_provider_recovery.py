import asyncio
import json

import httpx
import openai
import pytest

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.memory import MemoryStream
from drift.providers import CallBudget


def ready(root):
    brain = Brain({'name': 'recovery'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


def test_transient_timeout_retries_once_with_each_attempt_counted(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    capture = CaptureStore(str(tmp_path)).capture('Messy thought stays exact', 'retry-test')
    seen = []
    def provider(*args, **kwargs):
        seen.append(args)
        if len(seen) == 1:
            raise openai.APITimeoutError(request=httpx.Request('POST', 'http://127.0.0.1'))
        return {'text': 'An unverified summary.', 'tool_calls': [], 'output': [], 'usage': {}}
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    monkeypatch.setitem(config, 'max_provider_attempts', 2)
    asyncio.run(brain._think_once())
    assert len(seen) == 2
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 2
    assert CallBudget(str(tmp_path)).status()['failures'] == 1
    assert brain.tasks.list_tasks()[0].attempt_count == 2
    reopened = CaptureStore(str(tmp_path)).get(capture['capture']['id'])
    assert reopened['text'] == 'Messy thought stays exact'
    assert reopened['status'] == 'processed'


def test_capture_processing_does_not_request_unnecessary_tools(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    CaptureStore(str(tmp_path)).capture('Organize this thought without taking actions', 'tools-test')
    seen = []
    def provider(items, tools=True, instructions=None, max_tokens=300, **kwargs):
        seen.append(tools)
        return {'text': 'An unverified summary.', 'tool_calls': [], 'output': [], 'usage': {}}
    monkeypatch.setattr('drift.brain.chat', provider)
    asyncio.run(brain._think_once())
    assert seen == [False]


def test_transient_failures_stop_and_idle_does_not_repeat(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    capture = CaptureStore(str(tmp_path)).capture('Keep this even with a dead provider', 'stop-test')
    seen = []
    def provider(*args, **kwargs):
        seen.append(1)
        raise openai.APITimeoutError(request=httpx.Request('POST', 'http://127.0.0.1'))
    monkeypatch.setattr('drift.providers._chat_completions', provider)
    monkeypatch.setitem(config, 'max_provider_attempts', 2)
    asyncio.run(brain._think_once())
    monkeypatch.setattr(brain, '_create_attention_task', lambda: None)
    asyncio.run(brain._think_once())
    assert len(seen) == 2
    assert CaptureStore(str(tmp_path)).get(capture['capture']['id'])['status'] == 'needs_review'


def test_non_transient_failure_is_not_retried(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    task = brain.tasks.create_task('Review', 'Do not retry invalid requests')
    seen = []
    def provider(*args, **kwargs):
        seen.append(1)
        raise ValueError('Invalid request')
    monkeypatch.setattr('drift.brain.chat', provider)
    with pytest.raises(ValueError):
        asyncio.run(brain._invoke_model(task, [{'role': 'user', 'content': 'hello'}], 'rules'))
    assert len(seen) == 1


def test_retry_cannot_bypass_task_limit(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    task = brain.tasks.create_task('Review', 'Bound all physical calls')
    monkeypatch.setitem(config, 'max_model_calls_per_task', 1)
    seen = []
    def provider(*args, **kwargs):
        seen.append(1)
        raise openai.APITimeoutError(request=httpx.Request('POST', 'http://127.0.0.1'))
    monkeypatch.setattr('drift.brain.chat', provider)
    with pytest.raises(RuntimeError, match='task model-call limit'):
        asyncio.run(brain._invoke_model(task, [{'role': 'user', 'content': 'hello'}], 'rules'))
    assert len(seen) == 1
