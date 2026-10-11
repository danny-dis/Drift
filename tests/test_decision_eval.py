import json

from drift.decision_eval import evaluate_jsonl, main


def test_eval_reports_proxy_agreement_calibration_and_unavailable_policy_metrics(tmp_path):
    data = tmp_path / "decisions.jsonl"
    data.write_text(json.dumps({"question": "importance", "prediction": 8, "confidence": 0.8,
                                "label": 9, "latency_ms": 4}) + "\n" +
                    json.dumps({"question": "importance", "prediction": 2, "confidence": 0.4,
                                "label": 1, "latency_ms": 6}) + "\n")
    summary = evaluate_jsonl(data)
    assert summary["count"] == 2
    assert summary["agreement"] == 0.0
    assert summary["mean_absolute_error"] == 1.0
    assert summary["mean_latency_ms"] == 5
    assert summary["false_promotion"] == "unavailable"
    assert summary["quality_scope"] == "labeled lexical proxy; not semantic quality"


def test_eval_cli_with_synthetic_jsonl(tmp_path, capsys):
    data = tmp_path / "fixture.jsonl"
    data.write_text('{"prediction":true,"label":true}\n')
    assert main([str(data)]) == 0
    assert '"count": 1' in capsys.readouterr().out
