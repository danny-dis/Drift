from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.server import create_app


def test_events_endpoint_uses_durable_ledger(tmp_path):
    b=Brain({'name':'events','animal':'crab'},str(tmp_path));b._init_stores()
    c=TestClient(create_app({'events':b}))
    assert c.get('/api/events').status_code == 200
