import json

from drift.brain import Brain
from drift.loop_decisions import inspect_batch


def test_explicit_low_salience_owner_message_always_preempts_idle(tmp_path):
    brain = Brain({"name": "test"}, str(tmp_path))
    brain._low_value_streak = 99
    for message in ("ok", "ping"):
        brain._user_message = message
        proceed, reason = brain.should_think(False)
        assert proceed is True
        assert "owner" in reason


def test_batch_inspection_is_deterministic_bounded_and_retains_high_value(tmp_path):
    events = [
        {"name": "note.md", "content": "Please investigate this serious outage and preserve its evidence."},
        {"name": "noise.txt", "content": "ok"},
    ]
    first = inspect_batch(events)
    assert first == inspect_batch(events)
    assert first["action"] == "research"
    assert len(first["items"]) == 2
    assert all(len(item["name"]) <= 240 for item in first["items"])


def test_low_noise_inbox_idles_and_persists_compact_counters(tmp_path):
    brain = Brain({"name": "test"}, str(tmp_path))
    brain._inbox_pending = [{"name": "ping.txt", "content": "ok"}]
    proceed, _ = brain.should_think(False)
    assert proceed is False
    assert brain._inbox_pending == []
    status = brain.decision_status()
    assert status["skipped_low"] == 1
    persisted = json.loads((tmp_path / "loop_decisions.json").read_text())
    assert persisted["skipped_low"] == 1


def test_high_value_inbox_is_not_dropped_or_hysteresis_gated(tmp_path):
    brain = Brain({"name": "test"}, str(tmp_path))
    brain._low_value_streak = 99
    event = {"name": "incident.md", "content": "Investigate a critical security incident and assess impact."}
    brain._inbox_pending = [event]
    proceed, _ = brain.should_think(False)
    assert proceed is True
    assert brain._inbox_pending == [event]
    assert brain.decision_status()["missed_high_value"] is None  # no labeled counterfactual


def test_internal_loop_telemetry_is_excluded_from_inbox(tmp_path):
    brain = Brain({"name": "test"}, str(tmp_path))
    for name in ("loop_decisions.json", "decision_status.json", ".loop_decisions.json"):
        assert name in Brain._IGNORE_FILES or name.startswith(".")
    assert "loop_decisions.json" in Brain._IGNORE_FILES
    assert "decision_status.json" in Brain._IGNORE_FILES
