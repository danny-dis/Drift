"""Controller acceptance at loop, memory, provider, and telemetry boundaries."""
import json

from drift.brain import Brain
from drift.config import config
from drift.decisions import DecisionService, build_decision_payload
from drift.decision_eval import evaluate_jsonl
from drift.memory import MemoryStream


class Provider:
    remote = False
    def __init__(self, value=None, confidence=.95):
        self.value = value
        self.confidence = confidence
        self.calls = []
    def decide(self, state, questions):
        self.calls.append((state, questions))
        return {"answers": {q["id"]: {"value": self.value if self.value is not None else q["default"],
                                       "confidence": self.confidence} for q in questions},
                "provider": "fixture", "model": "fixture-1"}


def test_low_confidence_provider_cannot_override_safe_default(tmp_path):
    service = DecisionService({"enabled": True}, Provider(value=True, confidence=.01), budget_root=str(tmp_path))
    result = service.decide("scope", [{"id": "retain", "type": "boolean", "default": False}])
    assert result["answers"]["retain"]["value"] is False
    assert result["fallback"] and result["status"] != "ok"


def test_nested_secrets_are_not_sent_and_state_has_a_total_cap(tmp_path):
    provider = Provider()
    service = DecisionService({"enabled": True, "max_state_chars": 200}, provider, budget_root=str(tmp_path))
    service.decide({"candidates": [{"content": "ok", "api_key": "NESTED_SECRET", "password": "SECOND_SECRET"}],
                    "text": "token=TEXT_SECRET " + "z" * 2000},
                   [{"id": "x", "type": "boolean", "default": False}])
    sent = json.dumps(provider.calls[0][0], ensure_ascii=False)
    assert not any(x in sent for x in ("NESTED_SECRET", "SECOND_SECRET", "TEXT_SECRET"))
    assert len(sent) <= 200


def test_decision_provider_respects_persisted_call_budget(tmp_path, monkeypatch):
    monkeypatch.setitem(config, "daily_max_model_calls", 1)
    provider = Provider()
    q = [{"id": "x", "type": "boolean", "default": False}]
    service = DecisionService({"enabled": True}, provider, budget_root=str(tmp_path))
    service.decide("first", q)
    denied = service.decide("second", q)
    assert len(provider.calls) == 1
    assert denied["status"] != "ok" and denied["fallback"]


def test_memory_always_uses_service_and_keeps_explicit_kind_and_references(tmp_path, monkeypatch):
    monkeypatch.setattr("drift.memory.embed", lambda _: [])
    service = DecisionService({"enabled": False}, budget_root=str(tmp_path))
    stream = MemoryStream(str(tmp_path), decision_service=service)
    entry = stream.add("Fact: retained original content", kind="reflection", depth=2, references=["m_0000"])
    assert entry["content"] == "Fact: retained original content" and entry["kind"] == "reflection"
    assert entry["depth"] == 2 and entry["references"] == ["m_0000"]
    records = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(records) == 1
    assert "retained original content" not in records[0]
    assert MemoryStream(str(tmp_path)).memories[0]["decision"]["decision_id"]


def test_optional_reranking_fails_back_to_identical_retrieval(tmp_path, monkeypatch):
    monkeypatch.setattr("drift.memory.embed", lambda _: [])
    provider = Provider()
    service = DecisionService({"enabled": False}, provider, budget_root=str(tmp_path))
    stream = MemoryStream(str(tmp_path), decision_service=service)
    stream.add("First memory about queues")
    stream.add("Second memory about queues")
    initial = stream.retrieve("queues", top_k=2)
    monkeypatch.setitem(config, "decision_reranking_enabled", True)
    assert stream.retrieve("queues", top_k=2) == initial
    assert provider.calls == []


def test_optional_loop_provider_is_advisory_and_owner_preempts_it(tmp_path, monkeypatch):
    monkeypatch.setitem(config, "decision_loop_enabled", True)
    provider = Provider(value="ignore")
    brain = Brain({"name": "seam"}, str(tmp_path))
    brain._decision_service = DecisionService({"enabled": True}, provider, budget_root=str(tmp_path))
    brain._inbox_pending = [{"name": "outage.md", "content": "Investigate a critical incident."}]
    assert brain.should_think(False)[0] is True  # cannot suppress retained high-value evidence
    brain._user_message = "ok"
    assert brain.should_think(False)[0] is True


def test_gate_cannot_drop_uninspected_tail_or_nontrivial_unknown_input(tmp_path):
    brain = Brain({"name": "seam"}, str(tmp_path))
    brain._inbox_pending = [{"name": f"n-{i}.txt", "content": "ok"} for i in range(24)] + [
        {"name": "late.md", "content": "Investigate a critical incident with real evidence."}]
    assert brain.should_think(False)[0] is True
    assert brain._inbox_pending[-1]["name"] == "late.md"
    brain._inbox_pending = [{"name": "idea.md", "content": "A small device could detect when the tank is nearly empty."}]
    assert brain.should_think(False)[0] is True
    # No labeled counterfactual exists; metrics must not be treated as quality proof.
    assert brain.decision_status()["action"] == "research"


def test_generic_jev_payload_uses_requested_typed_questions_and_model():
    payload = build_decision_payload("small", questions=[
        {"id": "action", "type": "choice", "options": ["research", "sleep"], "default": "sleep"},
        {"id": "reflect", "type": "boolean", "default": False}], model="typesafe/jev-1.13")
    assert payload["model"] == "typesafe/jev-1.13"
    assert set(payload["questions"]) == {"action", "reflect"}
    assert payload["questions"]["reflect"]["type"] == "boolean"


def test_evaluator_computes_policy_errors_only_with_labels(tmp_path):
    path = tmp_path / "records.jsonl"
    path.write_text(json.dumps({"prediction": True, "label": False, "decision_type": "promotion", "latency_ms": 2}) + "\n" +
                    json.dumps({"prediction": False, "label": True, "decision_type": "retain", "latency_ms": 4}) + "\n", encoding="utf-8")
    result = evaluate_jsonl(path)
    assert result["false_promotion"] == 1.0 and result["false_deletion"] == 1.0
    assert result["agreement"] == 0.0
