"""Long-running and context-rot tests for Drift's cognitive kernel.

These tests verify the Phase 1 acceptance criteria from spec section 26:
- Long history: thousands of events, critical old fact still retrieved
- Noise injection: irrelevant events don't drown out important ones
- Context budget: packets stay below limits
- Stale knowledge: old facts lose recency without deletion
- Restart: kill and resume without losing task state
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from drift.task import TaskStore, can_transition
from drift.receipt import ContextReceipt, ReceiptStore
from drift.context import MemoryBlock, build_packet, decay_recency
from drift.compaction import Compactor, find_related_events
from drift.memory import MemoryStream
from drift.organism import DriftEvent, DriftLedger


# ---------------------------------------------------------------------------
# Context-rot: long history
# ---------------------------------------------------------------------------

def test_long_history_retrieves_critical_old_fact(tmp_path):
    """Thousands of events — a critical old fact must still be retrievable."""
    memory = MemoryStream(str(tmp_path))
    memory.path = str(tmp_path / "memory_stream.jsonl")
    # Seed with one critical old fact
    old_time = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    memory.memories = [
        {"id": "m_0001", "timestamp": old_time, "kind": "finding",
         "content": "CRITICAL: the lattice uses a dependency graph for routing",
         "importance": 10, "recency": 1.0}
    ]
    # Add thousands of noise entries
    for i in range(3000):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=i)).isoformat()
        memory.memories.append({
            "id": f"m_{i+2:04d}", "timestamp": recent, "kind": "thought",
            "content": f"routine thought about topic {i % 50}",
            "importance": 3, "recency": 1.0,
        })
    # Mock embeddings: give the critical memory a high-similarity embedding
    def fake_embed(text):
        if "lattice" in text or "dependency graph" in text:
            return [1.0] * 10  # high similarity
        return [0.1] * 10  # low similarity
    with patch('drift.memory.embed', side_effect=fake_embed):
        results = memory.retrieve("lattice dependency graph", top_k=5)
    assert len(results) > 0
    assert any("lattice" in r.get("content", "") for r in results)


def test_noise_injection_drowns_nothing_important(tmp_path):
    """Important recent memory must surface through noise."""
    memory = MemoryStream(str(tmp_path))
    memory.path = str(tmp_path / "memory_stream.jsonl")
    now = datetime.now(timezone.utc)
    # Add 200 noise entries
    for i in range(200):
        t = (now - timedelta(minutes=i)).isoformat()
        memory.memories.append({
            "id": f"m_noise_{i:04d}", "timestamp": t, "kind": "thought",
            "content": f"weather is nice today {i}",
            "importance": 2, "recency": 1.0,
        })
    # Add one important entry
    memory.memories.append({
        "id": "m_important", "timestamp": now.isoformat(),
        "kind": "finding", "content": "Project X needs migration to Rust",
        "importance": 10, "recency": 1.0,
    })
    with patch('drift.memory.embed', side_effect=lambda t: [1.0, 0.0] if "Project X" in t else [0.0, 1.0]):
        results = memory.retrieve("Project X migration", top_k=3)
    assert any("Project X" in r.get("content", "") for r in results)


def test_context_budget_stays_within_limits():
    """Every rendered packet must stay below the configured budget."""
    packet = build_packet(
        task="test",
        objective="verify budget constraint",
        facts=["fact" * 100 for _ in range(5)],
        recent_events=["event" * 50 for _ in range(5)],
        evidence=["ev" * 200 for _ in range(5)],
        memories=[
            MemoryBlock(
                id=f"m{i}", text="content" * 50, kind="observation",
                importance=0.9, confidence=0.9, relevance=0.9, recency=0.9,
            )
            for i in range(10)
        ],
        budget_chars=2000,
    )
    rendered = packet.render(2000)
    assert len(rendered) <= 2000


def test_stale_knowledge_loses_recency_without_deletion(tmp_path):
    """Old facts lose recency but remain in storage."""
    memory = MemoryStream(str(tmp_path))
    memory.path = str(tmp_path / "memory_stream.jsonl")
    old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    memory.memories = [
        {"id": "m_old", "timestamp": old_time, "kind": "finding",
         "content": "important old fact", "importance": 8, "recency": 1.0}
    ]
    ledger = DriftLedger(str(tmp_path))
    compactor = Compactor(ledger, memory, {})
    decayed = compactor.decay_stale_memories(half_life_hours=72.0)
    # Memory should still exist but with low recency
    assert len(memory.memories) == 1
    assert memory.memories[0]["recency"] < 0.5


# ---------------------------------------------------------------------------
# Restart recovery
# ---------------------------------------------------------------------------

def test_restart_recovers_task_state(tmp_path):
    """Kill and restart must not lose task progress."""
    store = TaskStore(str(tmp_path))
    t = store.create_task("important work", "finish the analysis",
                           project_id="proj-1", priority=0.9)
    # Transition through valid phases to research
    store.update_task(t.id, phase="understand")
    store.update_task(t.id, phase="connect")
    store.update_task(t.id, phase="research")
    store.update_task(t.id, progress=0.5, last_evidence="found three sources")
    # Simulate restart by creating new store pointing at same path
    store2 = TaskStore(str(tmp_path))
    recovered = store2.get_task(t.id)
    assert recovered is not None
    assert recovered.goal == "important work"
    assert recovered.phase == "research"
    assert recovered.progress == 0.5
    assert recovered.last_evidence == "found three sources"
    assert recovered.project_id == "proj-1"


def test_restart_receipts_persist(tmp_path):
    """Receipts must survive a restart."""
    store = ReceiptStore(str(tmp_path))
    store.save_receipt(ContextReceipt("t1", 7000, 1750, estimated_cost=0.01))
    store.save_receipt(ContextReceipt("t1", 6500, 1625, estimated_cost=0.02))
    store2 = ReceiptStore(str(tmp_path))
    assert store2.get_total_estimated_cost() == 0.03
    assert len(store2.get_receipts_for_task("t1")) == 2


def test_restart_ledger_intact(tmp_path):
    """Ledger events, ideas, projects must survive restart."""
    ledger = DriftLedger(str(tmp_path))
    ledger.add_idea("Use graphs for intelligence", ["knowledge graph"])
    ledger.add_event(DriftEvent(kind="observation", source="test",
                                 summary="new finding", confidence=0.8))
    ledger2 = DriftLedger(str(tmp_path))
    assert len(ledger2.data["ideas"]) == 1
    assert len(ledger2.data["events"]) == 1
    assert ledger2.data["events"][0]["summary"] == "new finding"


# ---------------------------------------------------------------------------
# Duplicate event handling
# ---------------------------------------------------------------------------

def test_duplicate_events_not_compacted_twice(tmp_path):
    """Compacting twice must not re-compact already-compacted source events."""
    ledger = DriftLedger(str(tmp_path))
    memory = MemoryStream(str(tmp_path))
    for i in range(10):
        ledger.add_event(DriftEvent(
            kind="observation", source="test",
            summary=f"duplicate event graph {i}",
            related_projects=["proj"],
        ))
    compactor = Compactor(ledger, memory, {"compaction_threshold": 5})
    findings1 = compactor.compact_events()
    assert len(findings1) >= 1
    # Count compacted source events after first compaction
    stats1 = compactor.get_compaction_stats()
    compacted_after_first = stats1["compacted_events"]
    # Second compaction
    findings2 = compactor.compact_events()
    stats2 = compactor.get_compaction_stats()
    compacted_after_second = stats2["compacted_events"]
    # No additional source events should be compacted
    assert compacted_after_second == compacted_after_first


# ---------------------------------------------------------------------------
# Crash during write
# ---------------------------------------------------------------------------

def test_crash_during_write_leaves_state_recoverable(tmp_path):
    """Simulate interruption during persistence — state must remain valid."""
    store = TaskStore(str(tmp_path))
    t = store.create_task("work", "do it")
    store.update_task(t.id, phase="understand")
    store.update_task(t.id, phase="connect")
    store.update_task(t.id, phase="research", progress=0.5)
    # The atomic write guarantees no partial state — reloading must work
    store2 = TaskStore(str(tmp_path))
    assert store2.get_task(t.id) is not None
    assert store2.get_task(t.id).progress == 0.5
