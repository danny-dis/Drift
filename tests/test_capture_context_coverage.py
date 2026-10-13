import asyncio

import pytest

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.intake import stage_captures


def test_canonical_part_never_silently_loses_tail_to_small_inference_budget(tmp_path, monkeypatch):
    brain = Brain({"name": "coverage"}, str(tmp_path))
    brain._init_stores()
    original = ('Quoted "coffee"\n\\ cups and reusable bottles. ' * 40)
    capture = CaptureStore(tmp_path).capture(original)["capture"]
    stage_captures(brain)
    task = brain.tasks.get_next_task()
    monkeypatch.setitem(config, "context_max_chars", 250)
    with pytest.raises(ValueError, match="complete thought part"):
        brain._build_task_context(task)
    assert CaptureStore(tmp_path).get(capture["id"])["text"] == original


def test_context_refusal_marks_canonical_capture_for_review_without_inference(tmp_path, monkeypatch):
    import drift.brain as module
    from drift.memory import MemoryStream
    brain = Brain({"name": "coverage"}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    original = 'Coffee and reusable cups. ' * 60
    capture = CaptureStore(tmp_path).capture(original)["capture"]
    monkeypatch.setitem(config, "context_max_chars", 250)
    monkeypatch.setattr(module, "chat", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call model")))
    asyncio.run(brain._think_once())
    assert brain.tasks.list_tasks()[0].status == "blocked"
    result = CaptureStore(tmp_path).get(capture["id"])
    assert result["status"] == "needs_review"
    assert result["text"] == original


def test_capture_inference_keeps_unrelated_pending_signals_for_later(tmp_path, monkeypatch):
    import json
    import drift.brain as module
    from drift.memory import MemoryStream
    brain = Brain({"name": "coverage"}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path))
    brain._init_stores()
    CaptureStore(tmp_path).capture("A coffee cart with reusable cups.")
    brain._user_message = "UNRELATED: rotate credentials"
    brain._inbox_pending = [{"name": "privacy.txt", "content": "UNRELATED: password operations"}]
    seen = []
    def answer(input_list, *args, **kwargs):
        seen.extend(input_list)
        return {"text": json.dumps({"summary": "A coffee cart with reusable cups.", "qualification": "PARKED"}), "tool_calls": [], "output": []}
    monkeypatch.setattr(module, "chat", answer)
    asyncio.run(brain._think_once())
    assert len(seen) == 1
    assert json.loads(seen[0]["content"]) == {"original_thought_part": "A coffee cart with reusable cups."}
    assert brain._user_message == "UNRELATED: rotate credentials"
    assert brain._inbox_pending[0]["name"] == "privacy.txt"
