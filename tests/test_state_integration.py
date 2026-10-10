"""State-lane integration tests (owned by state worker).

Drives BOTH API route families against the SAME Brain stores, then
performs subsequent Brain writes + reload to prove no stale-ledger loss.
"""
from __future__ import annotations

import os
import types

from fastapi.testclient import TestClient

from drift.organism import DriftEvent, DriftLedger
from drift.server import create_app
from drift.task import TaskStore
from drift.receipt import ReceiptStore
from drift.memory import MemoryStream


def _make_brain(env_path: str):
    os.makedirs(env_path, exist_ok=True)
    brain = types.SimpleNamespace()
    brain.env_path = env_path
    brain.identity = {"name": "test", "animal": "crab"}
    brain.ledger = DriftLedger(env_path)
    brain.tasks = TaskStore(env_path)
    brain.receipts = ReceiptStore(env_path)
    brain.stream = MemoryStream(env_path)
    brain._broadcast = None

    async def _noop_broadcast(msg):
        return None

    brain._broadcast = _noop_broadcast
    # Minimal watcher stub with real interface
    watcher = types.SimpleNamespace()
    watcher._watched = {}

    def _register(pid, path):
        watcher._watched[pid] = path

    def _watched_projects():
        return list(watcher._watched.keys())

    watcher.register_project = _register
    watcher.get_watched_projects = _watched_projects
    brain.watcher = watcher
    return brain


def _client(tmp_path):
    env = str(tmp_path / "env")
    brain = _make_brain(env)
    app = create_app({"test": brain})
    return TestClient(app), brain, env


def test_store_identity_no_stale_loss(tmp_path):
    """Dashboard POST then Brain write then reload must keep the idea."""
    client, brain, env = _client(tmp_path)
    r = client.post("/api/organism/ideas", json={"text": "track stale ledger bug"})
    assert r.status_code == 200, r.text
    idea_id = r.json()["idea"]["id"]
    # Subsequent Brain write through Brain's own stores
    brain.ledger.add_event(DriftEvent(
        kind="observation", source="brain", summary="brain tick",
        confidence=0.5, evidence=[], related_projects=[], related_ideas=[],
    ))
    fresh = DriftLedger(env)
    assert any(i["id"] == idea_id for i in fresh.data["ideas"]), "idea lost after Brain write (stale ledger)"


def test_both_idea_endpoints_unified_pipeline_and_dedupe(tmp_path):
    client, brain, env = _client(tmp_path)
    r1 = client.post("/api/organism/ideas", json={"text": "Use graph databases for knowledge"})
    assert r1.status_code == 200, r1.text
    d1 = r1.json()["idea"]
    assert "graph" in (d1.get("concepts") or []), "concepts must be extracted"
    r2 = client.post("/api/ui/ideas", json={"text": "Use graph databases for knowledge"})
    assert r2.status_code == 200, r2.text
    # Each captured idea gets exactly one bounded task; re-capture dedupes per idea
    n_tasks = len(brain.tasks.list_tasks(limit=100))
    assert n_tasks == 2, f"expected one task per captured idea, got {n_tasks}"
    # Posting same text again via pipeline helper must not create unbounded tasks:
    # call qualify-free recapture through organism route with identical text is a new idea,
    # but re-POSTing an idea id path must dedupe — emulate by checking task count stable
    # when the same idea is processed twice through ensure helper (covered in unit below).
    from drift.pipeline import ensure_idea_task
    idea_id = d1["id"]
    t1 = ensure_idea_task(brain.ledger, brain.tasks, idea_id, d1["text"])
    t2 = ensure_idea_task(brain.ledger, brain.tasks, idea_id, d1["text"])
    assert t1.id == t2.id, "duplicate tasks created for the same idea"


def test_validation_and_status_codes(tmp_path):
    client, brain, env = _client(tmp_path)
    assert client.post("/api/organism/ideas", json={"text": "   "}).status_code == 400
    assert client.post("/api/organism/ideas", json={"text": "x" * 5000}).status_code == 400
    assert client.get("/api/ui/projects/nope").status_code == 404
    assert client.get("/api/organism/projects/nope/git").status_code == 404
    assert client.post("/api/ui/ideas", json={"text": ""}).status_code == 400
    # No brains -> 503 on ui family
    from drift.server import create_app as _mk
    from fastapi.testclient import TestClient as _TC
    app2 = _mk({})
    app2.state.drift_brains = {}
    c2 = _TC(app2)
    assert c2.get("/api/ui/projects").status_code == 503


def test_project_registration_watches_and_fail_closed(tmp_path):
    client, brain, env = _client(tmp_path)
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    r = client.post("/api/organism/projects", json={
        "name": "Graph DB", "repo": "user/graph-db", "local_path": str(proj_dir)})
    assert r.status_code == 200, r.text
    assert "graph-db" in brain.watcher.get_watched_projects()
    # drift-md write to registered path works
    w = client.post("/api/organism/projects/graph-db/drift-md", json={
        "state": "s", "findings": ["f"], "challenges": [], "alternatives": []})
    assert w.status_code == 200, w.text
    assert (proj_dir / "drift.md").exists()
    # unregistered project fails closed
    bad = client.post("/api/organism/projects/ghost/drift-md", json={
        "state": "s", "findings": [], "challenges": [], "alternatives": []})
    assert bad.status_code == 404
    # ui project registration reuses same logic + watch
    proj2 = tmp_path / "proj2"
    proj2.mkdir()
    r2 = client.post("/api/ui/projects", json={
        "name": "Second", "repo": "user/second", "local_path": str(proj2)})
    assert r2.status_code == 200, r2.text
    assert "second" in brain.watcher.get_watched_projects()


def test_research_store_and_session_endpoints(tmp_path):
    from drift.research import ResearchStore
    client, brain, env = _client(tmp_path)
    store = ResearchStore(env)
    s = store.start("graph db survey", strategy="targeted_lookup")
    assert s["id"] and s["state"] == "selecting"
    source = store.add_source(s["id"], "https://example.com/a", "Studies show graphs help.")
    done = store.finish(s["id"], {"findings": ["graphs help knowledge work"],
        "citations": [{"source_id": source["id"], "quote": "Studies show graphs help."}]})
    assert done["state"] == "complete" and done["verified"] is False
    assert store.get(s["id"])["report"]["findings"][0].startswith("graphs")
    assert len(store.list()) == 1
    # HTTP seams (lazy import inside handlers)
    r = client.post("/api/ui/research/sessions", json={
        "query": "graph db survey", "urls": ["https://example.com/a"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] and body["task_id"]
    sid = body["session_id"]
    assert client.get("/api/ui/research/sessions").status_code == 200
    g = client.get(f"/api/ui/research/sessions/{sid}")
    assert g.status_code == 200, g.text
    assert client.get("/api/ui/research/sessions/missing").status_code == 404
    assert client.post("/api/ui/research/sessions", json={"query": "  "}).status_code == 400
