from fastapi.testclient import TestClient

from drift.brain import Brain
from drift.providers import CallBudget
from drift.server import create_app


def test_usage_reads_persisted_box_counters_with_explicit_scopes(tmp_path):
    brain = Brain({"name": "usage"}, str(tmp_path))
    brain._init_stores()
    budget = CallBudget(brain.env_path)
    budget.record_call(True, 10, 5)
    budget.record_call(False)
    client = TestClient(create_app({"usage": brain}))
    value = client.get("/api/ui/usage").json()
    assert value["total_calls"] == 2
    assert value["calls"]["daily_calls"] == 2
    assert value["calls"]["weekly_tokens"] == 15
    assert value["failed"] == 1
    assert "week" in value["calls_scope"].lower()
    assert "lifetime" in value["failures_scope"].lower()
    assert "estimate" in value["cost_scope"].lower()
    assert value["successful"] is None
    assert value["by_capability"] is None
    assert value["by_provider"] is None
    restarted = Brain({"name": "usage"}, str(tmp_path))
    restarted._init_stores()
    assert TestClient(create_app({"usage": restarted})).get("/api/ui/usage").json()["total_calls"] == 2


def test_corrupt_usage_is_unavailable_not_a_fake_zero(tmp_path):
    brain = Brain({"name": "usage"}, str(tmp_path))
    brain._init_stores()
    (tmp_path / "call_budget.json").write_text("not json")
    response = TestClient(create_app({"usage": brain})).get("/api/ui/usage")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["total_calls"] is None
