"""Controller-owned end-to-end acceptance; no model calls."""
from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.memory import MemoryStream
from drift.organism import DriftLedger, DriftEvent
from drift.server import create_app


def test_dashboard_idea_survives_subsequent_brain_write(tmp_path):
    brain = Brain({'name': 'Acceptance', 'animal': 'fox', 'traits': {}}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    client = TestClient(create_app({'acceptance': brain}))
    response = client.post('/api/organism/ideas?crab=acceptance', json={'text': 'Research local-first evidence and project intelligence'})
    assert response.status_code == 200
    assert response.json()['ok'] is True
    idea_id = response.json()['idea']['id']
    assert any(i['id'] == idea_id for i in brain.ledger.data['ideas']), 'Dashboard capture is invisible to Brain'
    brain.ledger.add_event(DriftEvent(kind='observation', source='acceptance', summary='Brain continued working', confidence=1.0, evidence=[], related_projects=[], related_ideas=[]))
    reloaded = DriftLedger(str(tmp_path))
    assert any(i['id'] == idea_id for i in reloaded.data['ideas']), 'Accepted owner idea was lost during a Brain write'
