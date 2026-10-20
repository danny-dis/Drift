"""Offline work observations: no provider calls, no owner-box access."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from drift.work_activity import observe, record, safe_target, snapshot, tool_activity

TASK = SimpleNamespace(id="task-1", project_id="project-2", goal="Offline report")
FIELDS = {"kind", "active", "task_id", "project_id", "target", "at"}


def test_current_last_and_no_stale_project():
    brain = SimpleNamespace()
    assert snapshot(brain)["activity"]["project_id"] is None
    with observe(brain, task=TASK, tool="fetch_url", arguments={"url": "https://example.org/docs?q=private"}):
        current = snapshot(brain)["activity"]
        assert set(current) == FIELDS
        assert current["active"] and current["kind"] == "browsing"
        assert current["task_id"] == TASK.id and current["project_id"] == TASK.project_id
        assert current["target"] == "https://example.org/docs"
        assert current["at"].endswith("+00:00")
    saved = snapshot(brain)
    assert saved["activity"]["kind"] == "idle"
    assert saved["activity"]["project_id"] is None and saved["activity"]["task_id"] is None
    assert saved["last_activity"]["target"] == "https://example.org/docs"
    assert saved["last_activity"]["active"] is False
    with observe(brain, "thinking"):
        assert snapshot(brain)["activity"]["project_id"] is None
        assert snapshot(brain)["last_activity"]["kind"] == "browsing"
    assert snapshot(brain)["last_activity"]["task_id"] is None


def test_classification_and_fail_closed_privacy():
    for name, args, kind, target in [
        ("web_search", {"query": "password=private"}, "browsing", None),
        ("read_file", {"path": "nested/report.md"}, "reading", "report.md"),
        ("shell", {"command": "cat nested/report.md"}, "reading", "report.md"),
        ("edit_file", {"path": "nested/report.md"}, "writing", "report.md"),
        ("save_document", {"path": "notes.docx"}, "writing", "notes.docx"),
    ]:
        brain = SimpleNamespace()
        with observe(brain, task=TASK, tool=name, arguments=args):
            action = snapshot(brain)["activity"]
            assert (action["kind"], action["target"]) == (kind, target)
        assert "password" not in json.dumps(snapshot(brain))
    for value in [None, {}, "https://user:pass@example.org/path", "https://example.org/sk-abcdefghijklmnop", ".env", "password=private.txt", "a\nsecret.txt", "https://[broken", "https://example.org/%74oken/private"]:
        assert safe_target(value) is None
    assert safe_target(r"C:\work\report.md") == "report.md"
    assert tool_activity("shell", {"command": "cat a; echo secret"}) == (None, None)
    with observe(SimpleNamespace(), task=object(), tool=[], arguments=[]):
        pass
    brain = SimpleNamespace()
    with pytest.raises(RuntimeError):
        with observe(brain, "reading", TASK, "report.md"):
            raise RuntimeError("offline failure")
    assert snapshot(brain)["activity"]["active"] is False


def test_real_model_hook_with_stub_only(monkeypatch):
    from drift.brain import Brain
    import drift.brain as module
    brain = Brain.__new__(Brain)
    brain.env_path = "unused-offline-root"
    brain.tasks = SimpleNamespace(get_task=lambda _: SimpleNamespace(attempt_count=0), update_task=lambda *a, **k: None)
    brain._record_model_call = lambda *a: None
    brain._save_receipt = lambda *a: None
    calls = []
    def offline_chat(*args, **kwargs):
        calls.append(snapshot(brain)["activity"])
        return {"text": "offline", "usage": {}}
    monkeypatch.setattr(module, "chat", offline_chat)
    asyncio.run(brain._invoke_model(TASK, [], "offline"))
    asyncio.run(brain._invoke_model(None, [], "offline", tools=False))
    assert calls[0]["task_id"] == TASK.id and calls[0]["project_id"] == TASK.project_id
    assert calls[1]["task_id"] is None and calls[1]["project_id"] is None
    assert snapshot(brain)["activity"]["active"] is False


def test_actual_persisted_report_not_completion(tmp_path, monkeypatch):
    from drift.brain import Brain
    import drift.outcomes as outcomes
    brain = Brain.__new__(Brain)
    brain.env_path = str(tmp_path)
    brain.stream = None
    brain._retained_answer = lambda task: None
    brain._complete_report_task = lambda *args: None
    monkeypatch.setattr(outcomes, "record_answer", lambda *args: None)
    monkeypatch.setattr(outcomes, "finish_capture_task", lambda *args: None)
    asyncio.run(brain._finish_answer(TASK, "Synthetic offline report"))
    assert (tmp_path / "answers" / "task-1.md").is_file()
    action = snapshot(brain)["last_activity"]
    assert (action["kind"], action["target"], action["project_id"], action["active"]) == ("writing", "task-1.md", TASK.project_id, False)
    brain._retained_answer = lambda task: "retained"
    brain._work_activity = {"activity": snapshot(SimpleNamespace())["activity"], "last_activity": None}
    asyncio.run(brain._finish_answer(TASK, "ignored"))
    assert snapshot(brain)["last_activity"] is None


def test_status_exposes_snapshot_without_changing_guard(monkeypatch):
    import drift.server as server
    brain = SimpleNamespace(state="idle", thought_count=0, stream=None,
                            identity={"name": "Offline"}, position={"x": 0, "y": 0}, _focus_mode=False)
    request = object()
    def guarded(value):
        assert value is request
        return brain
    monkeypatch.setattr(server, "_get_brain", guarded)
    record(brain, "writing", TASK, "report.md")
    status = asyncio.run(server.get_status(request))
    assert status["activity"]["project_id"] is None
    assert status["last_activity"]["target"] == "report.md"
