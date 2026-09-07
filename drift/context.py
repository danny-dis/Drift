"""Bounded context construction for Drift.

Drift is a continuous process, not a continuously growing prompt.  This module
builds small task-specific context packets from durable state so cheap/local
models can operate without carrying the entire lifetime transcript.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextPacket:
    task: str
    objective: str
    facts: list[str] = field(default_factory=list)
    recent_events: list[str] = field(default_factory=list)
    relevant_ideas: list[str] = field(default_factory=list)
    project_state: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def render(self, budget_chars: int = 12000) -> str:
        sections = [
            f"TASK: {self.task}",
            f"OBJECTIVE: {self.objective}",
            self._section("STABLE FACTS", self.facts),
            self._section("RECENT EVENTS", self.recent_events),
            self._section("RELEVANT IDEAS", self.relevant_ideas),
            self._section("PROJECT STATE", self.project_state),
            self._section("CONSTRAINTS", self.constraints),
            self._section("EVIDENCE", self.evidence),
        ]
        text = "\n\n".join(s for s in sections if s)
        return text[:budget_chars]

    @staticmethod
    def _section(title: str, values: list[str]) -> str:
        if not values:
            return ""
        return title + "\n" + "\n".join(f"- {v}" for v in values)


def compact(items: list[Any], limit: int = 8) -> list[Any]:
    """Keep a deterministic bounded slice; callers should pre-rank by relevance."""
    return items[-limit:]


def build_packet(
    *,
    task: str,
    objective: str,
    facts: list[str] | None = None,
    recent_events: list[str] | None = None,
    relevant_ideas: list[str] | None = None,
    project_state: list[str] | None = None,
    constraints: list[str] | None = None,
    evidence: list[str] | None = None,
    budget_chars: int = 12000,
) -> ContextPacket:
    """Create a bounded context packet. Missing context is represented explicitly."""
    packet = ContextPacket(
        task=task,
        objective=objective,
        facts=compact(facts or []),
        recent_events=compact(recent_events or []),
        relevant_ideas=compact(relevant_ideas or []),
        project_state=compact(project_state or []),
        constraints=compact(constraints or []),
        evidence=compact(evidence or []),
    )
    packet.render(budget_chars)
    return packet
