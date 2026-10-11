"""Bounded offline evaluation for JSONL decision predictions and labels."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

MAX_ROWS = 100_000


def _equal(a, b):
    return a == b


def evaluate_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as source:
        for line_no, line in enumerate(source, 1):
            if len(rows) >= MAX_ROWS:
                raise ValueError(f"input exceeds {MAX_ROWS} rows")
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_no}") from exc
            if not isinstance(row, dict):
                continue
            rows.append(row)
    labeled = [r for r in rows if "label" in r and "prediction" in r]
    agreements = [_equal(r["prediction"], r["label"]) for r in labeled]
    numeric = []
    for row in labeled:
        p, label = row["prediction"], row["label"]
        if (isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p)
                and isinstance(label, (int, float)) and not isinstance(label, bool) and math.isfinite(label)):
            numeric.append(abs(p - label))
    confidences = [(r.get("confidence"), _equal(r["prediction"], r["label"])) for r in labeled
                   if isinstance(r.get("confidence"), (int, float))
                   and not isinstance(r.get("confidence"), bool)
                   and math.isfinite(r["confidence"]) and 0 <= r["confidence"] <= 1]
    latencies = [r["latency_ms"] for r in rows if isinstance(r.get("latency_ms"), (int, float))
                 and not isinstance(r.get("latency_ms"), bool) and math.isfinite(r["latency_ms"])]
    failures = sum(1 for r in rows if r.get("status") not in (None, "ok", "success"))
    promotion = [r for r in labeled if r.get("decision_type", r.get("question")) in ("promotion", "promote")
                 and isinstance(r["prediction"], bool) and isinstance(r["label"], bool)]
    retention = [r for r in labeled if r.get("decision_type", r.get("question")) in ("retain", "retention")
                 and isinstance(r["prediction"], bool) and isinstance(r["label"], bool)]
    negative_promotion = [r for r in promotion if r["label"] is False]
    positive_retention = [r for r in retention if r["label"] is True]
    false_promotion = sum(r["prediction"] is True for r in negative_promotion)
    false_deletion = sum(r["prediction"] is False for r in positive_retention)
    return {
        "count": len(rows), "labeled_count": len(labeled),
        "agreement": sum(agreements) / len(agreements) if agreements else None,
        "mean_absolute_error": statistics.mean(numeric) if numeric else None,
        "mean_confidence": statistics.mean(c for c, _ in confidences) if confidences else None,
        "confidence_accuracy_gap": abs(statistics.mean(c for c, _ in confidences)
                                        - statistics.mean(ok for _, ok in confidences)) if confidences else None,
        "mean_latency_ms": statistics.mean(latencies) if latencies else None,
        "failure_count": failures,
        "false_promotion": false_promotion / len(negative_promotion) if negative_promotion else "unavailable",
        "false_deletion": false_deletion / len(positive_retention) if positive_retention else "unavailable",
        "false_promotion_count": false_promotion if promotion else None,
        "false_deletion_count": false_deletion if retention else None,
        "policy_labeled_count": len(promotion) + len(retention),
        "quality_scope": "labeled lexical proxy; not semantic quality",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="offline JSONL predictions with optional explicit labels")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(evaluate_jsonl(args.jsonl), sort_keys=True))
    except (OSError, ValueError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
