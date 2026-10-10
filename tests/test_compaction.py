"""Tests for drift/compaction.py — event compaction and stale relevance decay."""
import pytest

from drift.compaction import (
    Compactor,
    find_related_events,
    summarize_event_group,
)
from drift.context import decay_recency
from drift.memory import MemoryStream
from drift.organism import DriftEvent, DriftLedger, git_snapshot


def test_find_related_events_groups_by_project(tmp_path):
    events = [
        {"summary": "alpha prototype launched", "related_projects": ["p1"], "evidence": []},
        {"summary": "beta prototype review", "related_projects": ["p1"], "evidence": []},
        {"summary": "weather report", "related_projects": ["p2"], "evidence": []},
    ]
    groups = find_related_events(events)
    assert len(groups) == 2
    for g in groups:
        if any("prototype" in e.get("summary", "") for e in g):
            assert len(g) == 2


def test_find_related_events_groups_by_concept(tmp_path):
    events = [
        {"summary": "graph database", "related_projects": [], "evidence": []},
        {"summary": "dependency graph", "related_projects": [], "evidence": []},
        {"summary": "weather", "related_projects": [], "evidence": []},
    ]
    groups = find_related_events(events)
    assert len(groups) >= 2


def test_find_related_events_no_relation():
    events = [
        {"summary": "cloud formation", "related_projects": [], "evidence": []},
        {"summary": "cryptography", "related_projects": [], "evidence": []},
    ]
    groups = find_related_events(events)
    assert len(groups) == 2


def test_summarize_event_group_truncation():
    long_text = "x" * 600
    group = [{"summary": long_text, "evidence": []}]
    result = summarize_event_group(group)
    assert len(result) <= 500


def test_should_compact_threshold(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    memory = MemoryStream(str(tmp_path))
    compactor = Compactor(ledger, memory, {})
    for i in range(55):
        ledger.add_event(DriftEvent(
            kind="observation", source="test", summary=f"event {i}"
        ))
    assert compactor.should_compact(event_count_threshold=50) is True


def test_compact_events_creates_findings(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    memory = MemoryStream(str(tmp_path))
    for i in range(10):
        ledger.add_event(DriftEvent(
            kind="observation", source="test",
            summary=f"graph analysis {i}",
            related_projects=["proj-graph"],
        ))
    compactor = Compactor(ledger, memory, {"compaction_threshold": 5})
    findings = compactor.compact_events()
    assert len(findings) >= 1
    stats = compactor.get_compaction_stats()
    assert stats["compacted_events"] == 10


def test_compact_events_empty(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    memory = MemoryStream(str(tmp_path))
    compactor = Compactor(ledger, memory, {})
    assert compactor.compact_events() == []


def test_decay_stale_memories(tmp_path):
    memory = MemoryStream(str(tmp_path))
    from datetime import datetime, timezone, timedelta
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    memory.memories = [
        {"id": "m_0001", "timestamp": old_time, "kind": "thought",
         "content": "old memory", "importance": 8, "recency": 1.0}
    ]
    memory.path = str(tmp_path / "memory_stream.jsonl")
    from drift.compaction import Compactor
    ledger = DriftLedger(str(tmp_path))
    compactor = Compactor(ledger, memory, {})
    decayed = compactor.decay_stale_memories(half_life_hours=72.0)
    assert decayed >= 1


def test_get_compaction_stats(tmp_path):
    ledger = DriftLedger(str(tmp_path))
    memory = MemoryStream(str(tmp_path))
    ledger.add_event(DriftEvent(
        kind="observation", source="test", summary="event 1"
    ))
    ledger.add_event(DriftEvent(
        kind="finding", source="compaction", summary="findings"
    ))
    compactor = Compactor(ledger, memory, {})
    stats = compactor.get_compaction_stats()
    assert stats["total_events"] == 2
    assert stats["findings_count"] == 1
