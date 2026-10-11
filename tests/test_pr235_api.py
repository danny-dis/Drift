"""Controller-owned API seams for decisions and explicit research repair."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from drift.brain import Brain
from drift.memory import MemoryStream
from drift.research import ResearchStore
from drift.server import create_app


def setup(tmp_path):
    br = Brain({"name": "seam"}, str(tmp_path))
    br.stream = MemoryStream(str(tmp_path))
    br._init_stores()
    return br, TestClient(create_app({"seam": br}))


def test_decisions_endpoint_is_read_only_and_does_not_expose_memory(tmp_path, monkeypatch):
    br, client = setup(tmp_path)
    secret = "PRIVATE_CONTENT_DO_NOT_EXPOSE"
    (tmp_path / "decisions.jsonl").write_text(json.dumps({
        "provider": "fixture", "model": "fixture-v1", "status": "ok",
        "latency_ms": 3, "fallback": None, "answers": {"x": {"value": secret}},
    }) + "\n", encoding="utf-8")
    res = client.get("/api/ui/decisions")
    assert res.status_code == 200
    assert "loop" in res.json() and "memory" in res.json()
    assert secret not in res.text
    assert br.tasks.list_tasks() == []
    monkeypatch.setenv("DRIFT_API_TOKEN", "fixture-auth")
    assert client.get("/api/ui/decisions").status_code == 401
    assert client.get("/api/ui/decisions", headers={"Authorization": "Bearer fixture-auth"}).status_code == 200


def test_resume_research_keeps_sources_and_does_not_create_another_task(tmp_path):
    br, client = setup(tmp_path)
    ids = client.post("/api/ui/research/sessions", json={"query": "source-linked repair"}).json()
    store = ResearchStore(str(tmp_path))
    src = store.add_source(ids["session_id"], "https://example.com/source", "Retained exact source.")
    store.finish(ids["session_id"], {"findings": ["invalid"], "citations": [{"source_id": "absent"}]})
    br.tasks.update_task(ids["task_id"], phase="blocked", status="blocked", blockers=["needs review"])
    count = len(br.tasks.list_tasks())
    resumed = client.post(f"/api/ui/research/sessions/{ids['session_id']}/resume", json={})
    assert resumed.status_code == 200, resumed.text
    assert len(br.tasks.list_tasks()) == count
    assert br.tasks.get_task(ids["task_id"]).status == "pending"
    got = store.get(ids["session_id"])
    assert got["sources"][0]["id"] == src["id"]
    assert got["repairs"] == 1
    assert client.post("/api/ui/research/sessions/missing/resume", json={}).status_code == 404


def test_resume_completed_or_exhausted_research_is_rejected(tmp_path):
    br, client = setup(tmp_path)
    store = ResearchStore(str(tmp_path))
    ids = client.post("/api/ui/research/sessions", json={"query": "bounded repair"}).json()
    src = store.add_source(ids["session_id"], "https://example.com/a", "Evidence")
    bad = {"findings": ["invalid"], "citations": [{"source_id": "unknown"}]}
    store.finish(ids["session_id"], bad)
    store.finish(ids["session_id"], bad)
    br.tasks.update_task(ids["task_id"], phase="blocked", status="blocked")
    assert client.post(f"/api/ui/research/sessions/{ids['session_id']}/resume", json={}).status_code == 409
    done = client.post("/api/ui/research/sessions", json={"query": "done"}).json()
    source = store.add_source(done["session_id"], "https://example.com/b", "Evidence")
    store.finish(done["session_id"], {"findings": ["advisory finding"], "citations": [{"source_id": source["id"]}]})
    assert client.post(f"/api/ui/research/sessions/{done['session_id']}/resume", json={}).status_code == 409


def test_prepare_research_records_real_fetch_and_reuses_retained_source(tmp_path, monkeypatch):
    import asyncio
    br, client = setup(tmp_path)
    ids = client.post("/api/ui/research/sessions", json={
        "query": "bounded fetch lineage", "urls": ["https://example.com/evidence"]}).json()
    calls = []
    def fetch(name, args, root):
        calls.append(name)
        return "Exact retained evidence for controller integration test."
    monkeypatch.setattr("drift.brain.execute_tool", fetch)
    task = br.tasks.get_task(ids["task_id"])
    store, session = asyncio.run(br._prepare_research(task))
    assert calls == ["fetch_url"] and len(session["sources"]) == 1
    assert session["tools"][-1]["name"] == "fetch_url"
    assert session["checkpoint"]["phase"] == "researching"
    _, resumed = asyncio.run(br._prepare_research(task))
    assert calls == ["fetch_url"]
    assert resumed["sources"][0]["id"] == session["sources"][0]["id"]


def test_invalid_session_payload_creates_no_orphan_task(tmp_path):
    br, client = setup(tmp_path)
    initial = len(br.tasks.list_tasks())
    for body in ({"query": "bad urls", "urls": ["file:///private"]},
                 {"query": "many urls", "urls": ["https://example.com/a"] * 11},
                 {"query": "non-string", "urls": [99]},
                 {"query": 99}, ["not object"]):
        res = client.post("/api/ui/research/sessions", json=body)
        assert res.status_code == 400, res.text
    assert len(br.tasks.list_tasks()) == initial
