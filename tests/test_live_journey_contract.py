"""End-to-end local runtime contracts; network/model adapters are fixtures."""
import asyncio
import json
from pathlib import Path
from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.memory import MemoryStream
from drift.research import ResearchStore
from drift.server import create_app
from drift.config import config


def test_research_task_source_report_episode_restart(tmp_path, monkeypatch):
    import drift.brain as module
    br = Brain({'name': 'journey'}, str(tmp_path)); br._init_stores(); br.stream = MemoryStream(str(tmp_path))
    client = TestClient(create_app({'journey': br}))
    response = client.post('/api/ui/research/sessions', json={'query': 'Explain Python pathlib',
        'urls': ['https://docs.python.org/3/library/pathlib.html']})
    assert response.status_code == 200
    ids = response.json(); calls = []
    monkeypatch.setattr(module, 'execute_tool', lambda name, args, root:
        'Pathlib provides object-oriented filesystem paths.')
    def model(*args, **kwargs):
        calls.append(1)
        session = ResearchStore(str(tmp_path)).get(ids['session_id'])
        assert len(session['sources']) == 1
        source = session['sources'][0]
        report = {'findings': ['Pathlib provides object-oriented filesystem paths.'],
                  'citations': [{'source_id': source['id'], 'quote': 'Pathlib provides object-oriented filesystem paths.'}]}
        return {'text': json.dumps(report), 'tool_calls': [], 'output': [], 'model': 'fixture'}
    monkeypatch.setattr(module, 'chat', model)
    asyncio.run(br._think_once())
    result = ResearchStore(str(tmp_path)).get(ids['session_id'])
    assert result['state'] == 'complete' and result['verified'] is False
    assert result['citation_integrity_checked'] is True
    assert br.tasks.get_task(ids['task_id']).status == 'complete'
    assert len(calls) == 1
    assert (tmp_path / 'research' / (ids['session_id'] + '.md')).exists()
    assert (tmp_path / 'answers' / (ids['task_id'] + '.md')).exists()
    assert any(m['kind'] == 'episode' for m in MemoryStream(str(tmp_path)).memories)
    assert len(br.receipts.get_receipts_for_task(ids['task_id'])) == 1
    asyncio.run(br._think_once())
    assert len(calls) == 1  # no gratuitous idle generation


def test_task_call_limit_blocks_before_network(tmp_path, monkeypatch):
    import drift.brain as module
    br = Brain({'name': 'caps'}, str(tmp_path)); br._init_stores()
    task = br.tasks.create_task('bounded work', 'bounded work')
    br.tasks.update_task(task.id, attempt_count=2)
    task = br.tasks.get_task(task.id)
    monkeypatch.setitem(config, 'max_model_calls_per_task', 2)
    called = []
    monkeypatch.setattr(module, 'chat', lambda *a, **k: called.append(1))
    import pytest
    with pytest.raises(RuntimeError):
        asyncio.run(br._invoke_model(task, [{'role': 'user', 'content': 'work'}], 'rules'))
    assert called == []
    assert br.tasks.get_task(task.id).status == 'blocked'
