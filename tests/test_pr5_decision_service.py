import json
import math

from drift.decisions import DecisionService


def test_typed_batch_validates_and_reports_identity(tmp_path):
    class Provider:
        def decide(self, state, questions):
            return {"answers": {"s": {"value": 2.5, "confidence": 0.8},
                                "c": {"value": "keep", "confidence": 0.7},
                                "b": {"value": True, "confidence": 0.9}},
                    "provider": "fake", "model": "fixed-v1", "usage": {"input_tokens": 4}}

    service = DecisionService(settings={"enabled": True}, provider=Provider(), budget_root=str(tmp_path))
    result = service.decide({"text": "private memory"}, [
        {"id": "s", "type": "score", "min": 0, "max": 5, "default": 1},
        {"id": "c", "type": "choice", "options": ["keep", "drop"], "default": "keep"},
        {"id": "b", "type": "boolean", "default": False},
    ])
    assert result["answers"]["s"]["value"] == 2.5
    assert result["provider"] == "fake" and result["model"] == "fixed-v1"
    assert result["decision_id"] and result["schema_version"]
    assert result["status"] == "ok" and result["fallback"] is None
    assert "private memory" not in (tmp_path / "decisions.jsonl").read_text()


def test_invalid_or_nonfinite_answer_falls_back_safely(tmp_path):
    class Provider:
        def decide(self, state, questions):
            return {"answers": {"x": {"value": math.inf, "confidence": 2}}}

    service = DecisionService(settings={"enabled": True}, provider=Provider(), budget_root=str(tmp_path))
    result = service.decide("secret", [{"id": "x", "type": "score", "min": 0, "max": 9, "default": 3}])
    assert result["answers"]["x"]["value"] == 3
    assert result["fallback"] and result["status"] != "ok"


def test_remote_disallowed_in_free_only_and_state_allowlisted():
    seen = []
    class Provider:
        remote = True
        def decide(self, state, questions):
            seen.append(state)
            return {"answers": {"x": {"value": True, "confidence": 0.5}}}

    questions = [{"id": "x", "type": "boolean", "default": False}]
    blocked = DecisionService(settings={"enabled": True, "free_only": True, "remote_opt_in": True}, provider=Provider())
    assert blocked.decide({"content": "secret"}, questions)["answers"]["x"]["value"] is False
    assert not seen
    allowed = DecisionService(settings={"enabled": True, "free_only": False, "remote_opt_in": True,
                                        "allowed_state_fields": ["safe"], "max_state_chars": 40}, provider=Provider())
    allowed.decide({"safe": "yes", "content": "secret", "api_key": "token"}, questions)
    assert seen and "secret" not in json.dumps(seen)
