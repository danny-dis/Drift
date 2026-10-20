"""A real SDK error after a tool turn must not leak its body to logs."""
import asyncio
import logging
from unittest.mock import AsyncMock

import httpx
import openai

from drift.brain import Brain
from drift.memory import MemoryStream


def test_tool_followup_error_logs_only_type_and_retains_original(tmp_path, monkeypatch, caplog):
    from drift import brain as module
    marker = 'SYNTHETIC_PRIVATE_FOLLOWUP_BODY_022'
    original = 'Retain this synthetic owner instruction unchanged.'
    brain = Brain({'name': 'privacy-fixture'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    task = brain.tasks.create_task('Review a local note', 'Read before summarizing', source_text=original)
    monkeypatch.setattr(brain, 'should_think', lambda pending: (True, 'fixture'))
    monkeypatch.setattr(brain, '_prepare_research', AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(brain, '_build_task_context', lambda task: ('Synthetic instructions', [], {}))
    monkeypatch.setattr(module, 'execute_tool', lambda *args: 'Synthetic local note')
    monkeypatch.setattr(brain, '_emit', AsyncMock())
    monkeypatch.setattr(brain, '_broadcast', AsyncMock())
    monkeypatch.setattr(brain, '_emit_api_call', AsyncMock())
    with openai.OpenAI(api_key='offline-fixture') as client:
        error = client._make_status_error_from_response(httpx.Response(400,
            request=httpx.Request('POST', 'http://127.0.0.1:1/v1/chat/completions'),
            json={'error': marker}))
    invoke = AsyncMock(side_effect=[{'text': None, 'output': [], 'tool_calls': [
        {'name': 'read_file', 'arguments': {'path': 'note.md'}, 'call_id': 'fixture'}]}, error])
    monkeypatch.setattr(brain, '_invoke_model', invoke)
    caplog.set_level(logging.ERROR, logger='drift.brain')
    asyncio.run(brain._think_once())
    assert invoke.await_count == 2
    assert marker not in caplog.text
    assert 'BadRequestError' in caplog.text
    retained = brain.tasks.get_task(task.id)
    assert retained.status == 'blocked'
    assert retained.source_text == original
    assert all(marker not in blocker for blocker in retained.blockers)
    assert brain.state == 'idle'
