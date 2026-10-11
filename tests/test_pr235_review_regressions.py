"""Regression tests for concrete Luna release-review findings."""
import json

from drift.decisions import DecisionService
from drift.research import ResearchStore
from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.memory import MemoryStream
from drift.server import create_app


def setup(tmp_path):
    brain = Brain({"name": "review"}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    return brain, TestClient(create_app({"review": brain}))


class CaptureProvider:
    remote = False
    def __init__(self):
        self.states = []
    def decide(self, state, questions):
        self.states.append(state)
        return {"answers": {q["id"]: {"value": q["default"], "confidence": .9} for q in questions}}


def test_recognizable_credential_formats_do_not_reach_provider(tmp_path):
    # Deliberately synthetic, nonfunctional format fixtures, never real credentials.
    specimens = ["ghp_" + "0" * 36, "github_pat_" + "0" * 70,
                 "AKIA" + "0" * 16, "ASIA" + "0" * 16,
                 "aB1/" * 10,
                 "-----BEGIN PRIVATE KEY-----\nDUMMY\n-----END PRIVATE KEY-----"]
    provider = CaptureProvider()
    service = DecisionService({"enabled": True}, provider, budget_root=str(tmp_path))
    for specimen in specimens:
        service.decide({"text": "credential-shaped fixture: " + specimen},
                       [{"id": "x", "type": "boolean", "default": False}])
        assert specimen not in json.dumps(provider.states[-1])
        assert "[REDACTED]" in json.dumps(provider.states[-1])


def test_failed_task_update_is_recoverable_without_spending_another_attempt(tmp_path, monkeypatch):
    brain, client = setup(tmp_path)
    ids = client.post("/api/ui/research/sessions", json={"query": "recoverable repair"}).json()
    store = ResearchStore(str(tmp_path))
    store.add_source(ids["session_id"], "https://example.com/a", "Exact retained evidence.")
    store.finish(ids["session_id"], {"findings": ["unverified"], "citations": []})
    brain.tasks.update_task(ids["task_id"], phase="blocked", status="blocked")
    update = brain.tasks.update_task
    def failed(*args, **kwargs):
        raise OSError("fixture persistence error")
    monkeypatch.setattr(brain.tasks, "update_task", failed)
    response = client.post(f"/api/ui/research/sessions/{ids['session_id']}/resume", json={})
    assert response.status_code == 503
    interrupted = store.get(ids["session_id"])
    assert interrupted["repair_pending"] and interrupted["owner_repair_attempts"] == 1
    monkeypatch.setattr(brain.tasks, "update_task", update)
    response = client.post(f"/api/ui/research/sessions/{ids['session_id']}/resume", json={})
    assert response.status_code == 200, response.text
    recovered = ResearchStore(str(tmp_path)).get(ids["session_id"])
    assert recovered["repair_pending"] is False and recovered["owner_repair_attempts"] == 1
    assert recovered["sources"] == interrupted["sources"]
    assert len(brain.tasks.list_tasks()) == 1
    assert brain.tasks.get_task(ids["task_id"]).status == "pending"
