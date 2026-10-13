from fastapi.testclient import TestClient

from drift.brain import Brain
from drift.config import config
from drift.providers import CallBudget
from drift.server import create_app


def ready(tmp_path, monkeypatch):
    monkeypatch.delenv("DRIFT_API_TOKEN", raising=False)
    brain = Brain({"name": "setup"}, str(tmp_path))
    brain._init_stores()
    monkeypatch.setitem(config, "provider", "dmrx")
    monkeypatch.setitem(config, "base_url", "http://127.0.0.1:47113/v1")
    monkeypatch.setitem(config, "free_only", True)
    monkeypatch.setitem(config, "daily_max_model_calls", 200)
    monkeypatch.setitem(config, "weekly_max_model_calls", 200)
    return brain, TestClient(create_app({"setup": brain}))


def test_setup_reads_storage_without_claiming_or_calling_ai(tmp_path, monkeypatch):
    import drift.providers as providers
    brain, client = ready(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("unexpected inference")))
    response = client.get("/api/ui/setup")
    assert response.status_code == 200
    value = response.json()
    assert value["capture_ready"] is True
    assert value["storage_path"] == str(tmp_path.resolve())
    assert value["processing"]["state"] == "unchecked"
    assert value["processing"]["checked_at"] is None
    assert CallBudget(brain.env_path).status()["daily_calls"] == 0


def test_explicit_check_uses_one_real_admitted_call_without_tools(tmp_path, monkeypatch):
    import drift.providers as providers
    brain, client = ready(tmp_path, monkeypatch)
    seen = []
    def transport(input_list, tools, instructions, max_tokens):
        seen.append((tools, max_tokens))
        return {"text": "DRIFT_READY", "tool_calls": [], "output": [], "usage": {"prompt_tokens": 5, "completion_tokens": 3}}
    monkeypatch.setattr(providers, "_chat_completions", transport)
    response = client.post("/api/ui/setup/check", json={})
    assert response.status_code == 200
    assert response.json()["processing"]["state"] == "ready"
    assert response.json()["processing"]["checked_at"]
    assert seen == [(False, 24)]
    assert CallBudget(brain.env_path).status()["daily_calls"] == 1
    assert client.get("/api/ui/setup").json()["processing"]["state"] == "ready"


def test_unavailable_check_does_not_expose_secrets_or_block_capture(tmp_path, monkeypatch):
    import drift.providers as providers
    brain, client = ready(tmp_path, monkeypatch)
    def unavailable(*args, **kwargs):
        raise RuntimeError("private credential should-not-appear")
    monkeypatch.setattr(providers, "_chat_completions", unavailable)
    result = client.post("/api/ui/setup/check", json={})
    assert result.status_code == 200
    assert result.json()["processing"]["state"] == "unavailable"
    assert "should-not-appear" not in result.text
    assert client.post("/api/ui/captures", json={"text": "save without AI"}).status_code == 200
    assert CallBudget(brain.env_path).status()["failures"] == 1


def test_exhausted_budget_is_limited_not_ready(tmp_path, monkeypatch):
    import drift.providers as providers
    brain, client = ready(tmp_path, monkeypatch)
    monkeypatch.setitem(config, "daily_max_model_calls", 1)
    CallBudget(brain.env_path).reserve()
    monkeypatch.setattr(providers, "_chat_completions", lambda *a, **k: (_ for _ in ()).throw(AssertionError("budget bypass")))
    result = client.post("/api/ui/setup/check", json={})
    assert result.status_code == 200
    assert result.json()["processing"]["state"] == "limited"
    assert CallBudget(brain.env_path).status()["daily_calls"] == 1


def test_setup_respects_existing_session_token_and_origin_guards(tmp_path, monkeypatch):
    _, client = ready(tmp_path, monkeypatch)
    monkeypatch.setenv("DRIFT_API_TOKEN", "qa-session-only")
    assert client.get("/api/ui/setup").status_code == 401
    assert client.get("/api/ui/setup", headers={"Authorization": "Bearer qa-session-only"}).json()["auth_required"] is True
    assert client.post("/api/ui/setup/check", headers={"Origin": "https://foreign.example"}, json={}).status_code == 403
