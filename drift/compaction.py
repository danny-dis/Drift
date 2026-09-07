"""Event compaction and stale relevance decay for Drift's cognitive kernel.

Long-running work periodically compacts: raw events -> findings -> stable state.
Old raw events remain available in durable storage but do not remain in
active context. All logic here is deterministic and cheap — no model calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drift.context import decay_recency
from drift.memory import MemoryStream
from drift.organism import DriftEvent, DriftLedger

logger = logging.getLogger("drift.compaction")


# ---------------------------------------------------------------------------
# Free functions (pure grouping / summarization logic, easy to test)
# ---------------------------------------------------------------------------


def find_related_events(events: list[dict]) -> list[list[dict]]:
    """Group events by shared project_id or concept overlap.

    Two events are related when they share at least one ``related_projects``
    entry OR share at least one keyword-ish token (>=3 chars) from their
    ``summary`` / ``evidence`` text.  The grouping is transitive via a simple
    union-find so that chains (a~b, b~c) collapse into a single cluster.

    Returns a list of groups; each group preserves the original event order.
    """
    if not events:
        return []

    n = len(events)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def project_set(ev: dict) -> set[str]:
        return {str(p) for p in ev.get("related_projects", []) if p}

    def concept_set(ev: dict) -> set[str]:
        tokens: set[str] = set()
        for text in [ev.get("summary", ""), *ev.get("evidence", [])]:
            tokens.update(t.lower() for t in _TOKEN_RE.findall(str(text)) if len(t) >= 3)
        return tokens

    for i in range(n):
        for j in range(i + 1, n):
            ei, ej = events[i], events[j]
            # Shared project_id is a strong signal.
            if project_set(ei) & project_set(ej):
                union(i, j)
                continue
            # Otherwise fall back to lightweight concept overlap.
            ci, cj = concept_set(ei), concept_set(ej)
            if ci and cj and ci & cj:
                union(i, j)

    clusters: dict[int, list[dict]] = {}
    for idx, ev in enumerate(events):
        clusters.setdefault(find(idx), []).append(ev)
    return list(clusters.values())


_TOKEN_RE = __import__("re").compile(r"[a-z0-9_/-]+", __import__("re").I)


def summarize_event_group(group: list[dict]) -> str:
    """One-paragraph extractive summary of an event group.

    Concatenates unique ``summary`` strings (in original order), truncates to
    500 characters, and returns the result.  Deterministic — same group always
    yields the same summary.
    """
    seen: set[str] = set()
    parts: list[str] = []
    for ev in group:
        summary = (ev.get("summary") or "").strip()
        if summary and summary not in seen:
            seen.add(summary)
            parts.append(summary)
    text = ". ".join(parts)
    if len(text) > 500:
        text = text[:497] + "..."
    return text or "(no summary)"


# ---------------------------------------------------------------------------
# Compactor
# ---------------------------------------------------------------------------


@dataclass
class Compactor:
    """Periodically compact raw events into findings and decay stale memories."""

    ledger: DriftLedger
    memory_stream: MemoryStream
    config: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_compact(self, event_count_threshold: int = 50) -> bool:
        """True if the number of non-compacted recent events exceeds threshold.

        Only **active** (un-compacted, non-finding) events count toward the threshold so that
        we do not re-compact material that has already been synthesized.
        """
        active = [e for e in self.ledger.data.get("events", []) if not e.get("compacted") and e.get("kind") != "finding"]
        return len(active) >= event_count_threshold

    def compact_events(self) -> list[DriftEvent]:
        """Synthesize recent raw events into higher-level findings.

        Steps:
        1. Gather active (non-compacted) events from the ledger.
        2. Group related events via :func:`find_related_events`.
        3. Create a new ``DriftEvent(kind="finding")`` summarizing each group.
        4. Mark source events as ``compacted: True`` on the original dict.
        5. Persist the new finding events to the ledger.

        Returns the list of newly created finding events.
        """
        events = self.ledger.data.get("events", [])
        active_indices = [i for i, e in enumerate(events) if not e.get("compacted") and e.get("kind") != "finding"]
        active_events = [events[i] for i in active_indices]

        if not active_events:
            logger.debug("compact_events: no active events to compact")
            return []

        groups = find_related_events(active_events)
        findings: list[DriftEvent] = []

        for group in groups:
            summary = summarize_event_group(group)
            # Aggregate supporting metadata from the group.
            confidence = _mean(_float(e, "confidence") for e in group)
            related_projects = _unique(
                p for e in group for p in e.get("related_projects", [])
            )
            related_ideas = _unique(
                i for e in group for i in e.get("related_ideas", [])
            )
            evidence = _unique(
                ev for e in group for ev in e.get("evidence", [])
            )
            sources = _unique(e.get("source", "") for e in group if e.get("source"))
            source_label = "compaction:" + "+".join(sorted(sources)) if sources else "compaction"

            finding = DriftEvent(
                kind="finding",
                source=source_label,
                summary=summary,
                confidence=round(confidence, 3),
                evidence=list(evidence)[:20],
                related_projects=list(related_projects),
                related_ideas=list(related_ideas),
            )
            findings.append(finding)

            # Mark every source event as compacted so they are not re-synthesized.
            for ev in group:
                ev["compacted"] = True

        # Persist: append findings, save the ledger (which also writes events back).
        for f in findings:
            self.ledger.add_event(f)
        self.ledger.save()

        logger.info(
            "compact_events: created %d finding(s) from %d active event(s) in %d group(s)",
            len(findings), len(active_events), len(groups),
        )
        return findings

    def decay_stale_memories(self, half_life_hours: float = 72.0) -> int:
        """Update recency scores in the memory stream.

        Iterates over every memory entry, recomputes its recency via
        :func:`drift.context.decay_recency`, and updates the in-memory dict.
        Returns the count of memories whose recency dropped below 0.5 (i.e.
        crossed the "stale" threshold).
        """
        decayed_count = 0
        for mem in self.memory_stream.memories:
            timestamp = mem.get("timestamp", "")
            new_recency = decay_recency(timestamp, half_life_hours=half_life_hours)
            mem["recency"] = round(new_recency, 6)
            if new_recency < 0.5:
                decayed_count += 1

        if decayed_count:
            _persist_memory_stream(self.memory_stream)

        logger.info(
            "decay_stale_memories: %d stale (recency < 0.5) out of %d total",
            decayed_count, len(self.memory_stream.memories),
        )
        return decayed_count

    def get_compaction_stats(self) -> dict[str, int]:
        """Return a compact stats snapshot for observability."""
        events = self.ledger.data.get("events", [])
        total = len(events)
        compacted = sum(1 for e in events if e.get("compacted"))
        findings = sum(1 for e in events if e.get("kind") == "finding")
        return {
            "total_events": total,
            "compacted_events": compacted,
            "active_events": total - compacted,
            "findings_count": findings,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _float(ev: dict, key: str) -> float:
    try:
        return float(ev.get(key, 0.5))
    except (TypeError, ValueError):
        return 0.5


def _mean(values) -> float:
    vals = list(values)
    if not vals:
        return 0.5
    return sum(vals) / len(vals)


def _unique(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _persist_memory_stream(stream: MemoryStream) -> None:
    """Overwrite the memory_stream.jsonl with current in-memory state."""
    import os
    import json
    from pathlib import Path

    path = Path(stream.path)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        for mem in stream.memories:
            f.write(json.dumps(mem, ensure_ascii=False) + "\n")
    tmp.replace(path)


__all__ = [
    "Compactor",
    "find_related_events",
    "summarize_event_group",
]