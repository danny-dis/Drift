import asyncio

from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.config import config
from drift.memory import MemoryStream
from drift.providers import CallBudget
from drift.server import create_app


def ready(tmp_path):
    brain = Brain({'name': 'runtime'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    return brain, TestClient(create_app({'runtime': brain}))


def test_budget_explains_weekly_call_cap_separately_from_money(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    monkeypatch.setitem(config, 'daily_max_model_calls', 10)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 1)
    CallBudget(str(tmp_path)).reserve()
    result = client.get('/api/ui/budget').json()
    assert result['daily_remaining'] == result['daily_budget']
    assert result['calls']['weekly_calls'] == 1
    assert result['calls']['weekly_limit'] == 1
    assert result['calls']['can_call'] is False
    assert 'weekly' in result['waiting_reason'].lower()
    assert result['calls']['next_admission_at']


def test_model_failure_blocks_once_instead_of_silent_cycle_retries(tmp_path, monkeypatch):
    import drift.brain as module
    brain, _ = ready(tmp_path)
    task = brain.tasks.create_task('Investigate', 'Investigate safely')
    called = []
    def failed(*args, **kwargs):
        called.append(1)
        raise RuntimeError('fixture provider is unavailable')
    monkeypatch.setattr(module, 'chat', failed)
    asyncio.run(brain._think_once())
    assert brain.tasks.get_task(task.id).status == 'blocked'
    assert 'provider' in brain.tasks.get_task(task.id).blockers[0].lower()
    asyncio.run(brain._think_once())
    assert len(called) == 1


def test_empty_model_output_is_explicitly_reviewable(tmp_path, monkeypatch):
    import drift.brain as module
    brain, _ = ready(tmp_path)
    task = brain.tasks.create_task('Question', 'Answer question')
    monkeypatch.setattr(module, 'chat', lambda *a, **k: {'text': '', 'tool_calls': [], 'output': []})
    asyncio.run(brain._think_once())
    assert brain.tasks.get_task(task.id).status == 'blocked'
    assert 'empty' in brain.tasks.get_task(task.id).blockers[0].lower()
    assert brain.state == 'idle'
