import asyncio
import json
import threading

import httpx

from drift.brain import Brain
from drift.config import config
from drift.memory import MemoryStream
from drift.server import create_app


def ready(root):
    brain = Brain({'name': 'responsive'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


def test_capture_requests_remain_available_while_intake_is_waiting(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    started, release, ended = threading.Event(), threading.Event(), threading.Event()
    def slow_stage(_brain):
        started.set()
        try:
            release.wait(30)
        finally:
            ended.set()
    monkeypatch.setattr('drift.intake.stage_captures', slow_stage)
    async def exercise():
        cycle = asyncio.create_task(brain._think_once())
        try:
            assert await asyncio.to_thread(started.wait, 45)
            assert not ended.is_set(), 'Intake blocked the API event loop until its work finished'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app({'box': brain})), base_url='http://127.0.0.1') as client:
                response = await client.post('/api/ui/captures', json={'text': 'New thought while organization is waiting', 'client_id': 'while-staging'})
            assert response.status_code == 200
            assert response.json()['capture']['text'] == 'New thought while organization is waiting'
            assert not ended.is_set(), 'Capture only succeeded after background organization finished'
        finally:
            release.set()
            await cycle
    asyncio.run(exercise())


def test_late_owner_and_inbox_context_is_redacted_before_model_call(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    brain.tasks.create_task('Handle an owner note', 'Preserve intent safely')
    brain._user_message = 'api_key=fixture-not-a-real-credential'
    brain._inbox_pending = [{'name': 'note.txt', 'content': 'password=fixture-not-a-real-credential'}]
    monkeypatch.setitem(config, 'daily_max_model_calls', 200)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 200)
    observed = []
    def failing_provider(*args, **kwargs):
        observed.append(json.dumps([args, kwargs]))
        raise OSError('Injected unit-test provider failure')
    monkeypatch.setattr('drift.brain.chat', failing_provider)
    asyncio.run(brain._think_once())
    assert observed
    assert 'fixture-not-a-real-credential' not in observed[0]
    assert '[REDACTED]' in observed[0]
