"""Context receipt logging for Drift's cognitive kernel.

Every model call produces a compact receipt recording which memories were
selected, which were excluded by budget, and the estimated cost. Receipts
are append-only JSONL, dependency-free, and cheap enough to write on every
invocation without slowing the cognitive loop.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


RECEIPTS_FILENAME = "receipts.jsonl"


@dataclass
class ContextReceipt:
    """Compact record of one model call's context decisions."""

    task_id: str
    context_budget: int
    estimated_tokens: int
    selected_memory_ids: list[str] = field(default_factory=list)
    selection_scores: dict[str, float] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    excluded_high_score: list[str] = field(default_factory=list)
    model_provider: str = ""
    estimated_cost: float | None = None
    result_confidence: float | None = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def to_dict(receipt: ContextReceipt) -> dict[str, Any]:
    """Serialize a receipt to a JSON-compatible dict."""
    return {
        "task_id": receipt.task_id,
        "context_budget": receipt.context_budget,
        "estimated_tokens": receipt.estimated_tokens,
        "selected_memory_ids": list(receipt.selected_memory_ids),
        "selection_scores": dict(receipt.selection_scores),
        "evidence_ids": list(receipt.evidence_ids),
        "excluded_high_score": list(receipt.excluded_high_score),
        "model_provider": receipt.model_provider,
        "estimated_cost": receipt.estimated_cost,
        "result_confidence": receipt.result_confidence,
        "timestamp": receipt.timestamp,
    }


def from_dict(d: dict[str, Any]) -> ContextReceipt:
    """Deserialize a receipt from a JSON-compatible dict."""
    return ContextReceipt(
        task_id=d.get("task_id", ""),
        context_budget=int(d.get("context_budget", 0)),
        estimated_tokens=int(d.get("estimated_tokens", 0)),
        selected_memory_ids=list(d.get("selected_memory_ids", [])),
        selection_scores=dict(d.get("selection_scores", {})),
        evidence_ids=list(d.get("evidence_ids", [])),
        excluded_high_score=list(d.get("excluded_high_score", [])),
        model_provider=d.get("model_provider", ""),
        estimated_cost=d.get("estimated_cost"),
        result_confidence=d.get("result_confidence"),
        timestamp=d.get("timestamp", ""),
    )


class ReceiptStore:
    """Append-only JSONL store for context receipts."""

    def __init__(self, env_path: str) -> None:
        self.path = os.path.join(env_path, RECEIPTS_FILENAME)

    def save_receipt(self, receipt: ContextReceipt) -> None:
        """Append a single receipt to the JSONL file."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(to_dict(receipt)) + "\n")

    def _load_all(self) -> list[ContextReceipt]:
        """Load all receipts from disk; corrupt lines are skipped."""
        if not os.path.isfile(self.path):
            return []
        receipts: list[ContextReceipt] = []
        with open(self.path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    receipts.append(from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return receipts

    def get_receipts_for_task(self, task_id: str) -> list[ContextReceipt]:
        """Return all receipts for a given task, oldest first."""
        return [r for r in self._load_all() if r.task_id == task_id]

    def list_receipts(self, limit: int = 100) -> list[ContextReceipt]:
        """Return the most recent receipts, newest last."""
        all_receipts = self._load_all()
        return all_receipts[-limit:]

    def get_total_estimated_cost(self) -> float:
        """Sum estimated_cost across all receipts; None treated as 0."""
        total = 0.0
        for r in self._load_all():
            if r.estimated_cost is not None:
                total += r.estimated_cost
        return total