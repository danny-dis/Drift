"""Context engineering for Drift's continuous, model-agnostic cognition.

The key invariant is: *runtime history is not memory*. Every model invocation
gets a bounded working set assembled from durable state. The implementation
borrows the useful ideas behind memory hierarchies, compaction, tool-result
clearing and retrieval, but keeps them local and dependency-free so Drift can
run beside a cheap/local model.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable


@dataclass(frozen=True)
class MemoryBlock:
    """A durable fact/finding that can be paged into working context."""

    id: str
    text: str
    kind: str = "observation"
    importance: float = 0.5
    confidence: float = 0.5
    relevance: float = 0.5
    recency: float = 0.5
    provenance: tuple[str, ...] = ()
    created_at: str = ""

    def score(self) -> float:
        # Relevance dominates. Importance/confidence prevent a recent but weak
        # note from displacing a durable, well-supported architectural fact.
        return (
            0.45 * self.relevance
            + 0.25 * self.importance
            + 0.20 * self.confidence
            + 0.10 * self.recency
        )

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class ContextPacket:
    """Small, inspectable working memory for one bounded cognitive task."""

    task: str
    objective: str
    facts: list[str] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)
    relevant_ideas: list[str] = field(default_factory=list)
    project_state: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    memories: list[MemoryBlock] = field(default_factory=list)

    def render(self, budget_chars: int = 12000) -> str:
        """Render in priority order, never cutting through an arbitrary item.

        We reserve space for task/objective/constraints, then pack the highest
        scoring memory and evidence items. This is deliberately character based
        because Drift must work with arbitrary local providers/tokenizers.
        """
        budget = max(1000, budget_chars)
        header = [f"TASK: {self.task}", f"OBJECTIVE: {self.objective}"]
        for title, values in (
            ("STABLE FACTS", self.facts),
            ("PROJECT STATE", self.project_state),
            ("CONSTRAINTS", self.constraints),
        ):
            section = self._section(title, values)
            if section:
                header.append(section)
        text = "\n\n".join(header)
        remaining = budget - len(text) - 2

        # Durable memory is ranked instead of simply taking the newest records.
        ranked = sorted(self.memories, key=lambda m: m.score(), reverse=True)
        selected = self._pack_items(ranked, remaining)
        if selected:
            section = self._section("RELEVANT MEMORY", selected)
            text += "\n\n" + section
            remaining -= len(section) + 2

        # Events/ideas/evidence are cheap, but still bounded and packed whole.
        for title, values in (
            ("RECENT EVENTS", self.recent_events),
            ("RELEVANT IDEAS", self.relevant_ideas),
            ("EVIDENCE", self.evidence),
        ):
            packed = self._pack_strings(values, remaining)
            if not packed:
                continue
            section = self._section(title, packed)
            text += "\n\n" + section
            remaining -= len(section) + 2
            if remaining <= 0:
                break
        return text[:budget]

    @staticmethod
    def _section(title: str, values: Iterable[str]) -> str:
        values = [str(v).strip() for v in values if str(v).strip()]
        return title + "\n" + "\n".join(f"- {v}" for v in values) if values else ""

    @staticmethod
    def _pack_items(items: list[MemoryBlock], budget: int) -> list[str]:
        chosen: list[str] = []
        used = 0
        for item in items:
            line = f"[{item.kind}; confidence={item.confidence:.2f}; importance={item.importance:.2f}] {item.text}"
            if used + len(line) + 2 > max(0, budget):
                continue
            chosen.append(line)
            used += len(line) + 2
        return chosen

    @staticmethod
    def _pack_strings(values: list[str], budget: int) -> list[str]:
        chosen: list[str] = []
        used = 0
        for value in values:
            value = str(value).strip()
            if not value or used + len(value) + 2 > max(0, budget):
                continue
            chosen.append(value)
            used += len(value) + 2
        return chosen


def _tokens_approx(text: str) -> int:
    # Conservative rough estimate for providers where a tokenizer is not
    # available. This is only telemetry/guardrail; providers may use real
    # token counting at the dmr-X layer later.
    return max(1, math.ceil(len(text) / 4))


def salience(
    *, importance: float = 0.5, confidence: float = 0.5,
    relevance: float = 0.5, recency: float = 0.5,
) -> float:
    values = [max(0.0, min(1.0, float(v))) for v in (importance, confidence, relevance, recency)]
    return 0.45 * values[2] + 0.25 * values[0] + 0.20 * values[1] + 0.10 * values[3]


def decay_recency(created_at: str, half_life_hours: float = 72.0) -> float:
    """Return a bounded recency score; invalid timestamps are neutral."""
    try:
        stamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age_hours = max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 3600)
        return 0.5 ** (age_hours / max(1.0, half_life_hours))
    except (TypeError, ValueError):
        return 0.5


def keyword_relevance(query: str, text: str) -> float:
    """Cheap lexical relevance fallback; embeddings can replace this later."""
    q = set(re.findall(r"[a-z0-9_/-]{3,}", query.lower()))
    t = set(re.findall(r"[a-z0-9_/-]{3,}", text.lower()))
    if not q or not t:
        return 0.0
    return len(q & t) / len(q)


def compact(items: list[Any], limit: int = 8) -> list[Any]:
    """Compatibility helper: keep a deterministic bounded tail."""
    return items[-limit:]


def build_packet(
    *, task: str, objective: str, facts: list[str] | None = None,
    recent_events: list[str] | None = None, relevant_ideas: list[str] | None = None,
    project_state: list[str] | None = None, constraints: list[str] | None = None,
    evidence: list[str] | None = None, memories: list[MemoryBlock] | None = None,
    budget_chars: int = 12000,
) -> ContextPacket:
    packet = ContextPacket(
        task=task,
        objective=objective,
        facts=compact(facts or []),
        recent_events=compact(recent_events or []),
        relevant_ideas=compact(relevant_ideas or []),
        project_state=compact(project_state or []),
        constraints=compact(constraints or []),
        evidence=compact(evidence or []),
        memories=memories or [],
    )
    # Fail fast if the builder accidentally creates an unbounded packet.
    rendered = packet.render(budget_chars)
    if _tokens_approx(rendered) > max(250, budget_chars // 4):
        raise ValueError("context packet exceeded its configured budget")
    return packet
