import asyncio
import json

from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.memory import MemoryStream
from drift.server import create_app


def test_processed_thought_exposes_its_insights_without_replacing_original(tmp_path, monkeypatch):
    import drift.brain as module
    brain = Brain({'name': 'insights'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path)); brain._init_stores()
    client = TestClient(create_app({'insights': brain}))
    capture = client.post('/api/ui/captures', json={'text': '  A messy thought about persistence  '}).json()['capture']
    monkeypatch.setattr(module, 'chat', lambda *a, **k: {
        'text': json.dumps({'summary': 'Investigate persistent capture.', 'qualification': 'RESEARCH',
                            'questions': ['What survives a crash?']}), 'tool_calls': [], 'output': []})
    asyncio.run(brain._think_once())
    response = client.get(f"/api/ui/captures/{capture['id']}/insights")
    assert response.status_code == 200
    insights = response.json()
    assert insights['summaries'] == ['Investigate persistent capture.']
    assert insights['questions'] == ['What survives a crash?']
    assert insights['verified'] is False
    assert insights['progress'] == {'complete': 1, 'total': 1}
    assert client.get(f"/api/ui/captures/{capture['id']}").json()['capture']['text'] == capture['text']
    report = client.get(f"/api/ui/captures/{capture['id']}/report")
    assert report.status_code == 200
    assert 'unverified' in report.json()['text'].lower()


def test_unprocessed_capture_has_no_invented_insights(tmp_path):
    brain = Brain({'name': 'insights'}, str(tmp_path)); brain._init_stores()
    client = TestClient(create_app({'insights': brain}))
    capture = client.post('/api/ui/captures', json={'text': 'An unfinished fragment'}).json()['capture']
    data = client.get(f"/api/ui/captures/{capture['id']}/insights")
    assert data.status_code == 200
    assert data.json()['summaries'] == []
    assert data.json()['progress'] == {'complete': 0, 'total': 0}
    assert client.get(f"/api/ui/captures/{capture['id']}/report").status_code == 404
