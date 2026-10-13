import asyncio
import json
from pathlib import Path

from drift.brain import Brain
from drift.memory import MemoryStream
from drift.research import ResearchStore


def test_late_messages_cannot_cut_retained_evidence_json(tmp_path, monkeypatch):
    brain = Brain({'name': 'research'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    brain.tasks.create_task('Research', 'Compare research evidence')
    store = ResearchStore(str(tmp_path))
    session = store.start('Compare research evidence')
    for i in range(8):
        store.add_source(session['id'], f'https://example.com/{i}', f'Source {i}. ' + 'Research evidence matters. ' * 100)
    async def prepared(task):
        return store, store.get(session['id'])
    monkeypatch.setattr(brain, '_prepare_research', prepared)
    brain._user_message = 'Late owner context. ' * 200
    brain._inbox_pending = [{'name': 'owner.txt', 'content': 'Late inbox context. ' * 200}]
    observed = []
    def chat(items, tools, instructions, max_tokens, **kwargs):
        for item in items:
            if 'source_id' in item.get('content', ''):
                try:
                    json.loads(item['content'])
                    observed.append(True)
                except ValueError:
                    observed.append(False)
        return {'text': 'Insufficient evidence.', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', chat)
    asyncio.run(brain._think_once())
    assert observed == [True]


def test_create_workspace_uses_writable_working_root_not_installation(tmp_path, monkeypatch):
    from drift import server, runtime_resources
    install = tmp_path / 'installed' / 'drift'
    install.mkdir(parents=True)
    working = tmp_path / 'working'
    working.mkdir()
    monkeypatch.setattr(server, '__file__', str(install / 'server.py'))
    monkeypatch.setattr(runtime_resources, 'workspace_root', lambda: working)
    monkeypatch.setattr(server, 'brains', {})
    class BrainStub:
        def __init__(self, identity, box):
            self.identity = identity
        async def run(self):
            pass
    class Request:
        async def json(self):
            return {'name': 'release-test', 'animal': 'crab'}
    monkeypatch.setattr(server, 'Brain', BrainStub)
    result = asyncio.run(server.create_crab(Request()))
    assert result['ok']
    assert (working / 'release-test_box' / 'identity.json').is_file()
    assert not (install.parent / 'release-test_box').exists()
