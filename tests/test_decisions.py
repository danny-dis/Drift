"""Decisions module: deterministic default, JEV opt-in, never lose memory."""

import os

from drift import decisions
from drift.config import config
from drift.decisions import (
    DECISIONS_ENDPOINT,
    DECISIONS_MODEL,
    ResearchStore,
    build_decision_payload,
    decide_memory,
    should_idle_reflect,
)


def test_deterministic_default_no_remote():
    d = decide_memory("Fact: kelp grows near the window")
    assert d["provider"] == "lexical"
    assert d["retain"] is True
    assert 0 <= d["importance"] <= 9  # zero-indexed
    assert d["kind"] in ("thought", "fact", "lesson")
    assert "importance_display" in d and 1 <= d["importance_display"] <= 10


def test_malformed_timeout_schema_never_loses_memory():
    def boom(_payload):
        raise TimeoutError("network down")
    d = decide_memory("a memory worth keeping", caller=boom)
    assert d["retain"] is True and d["importance"] >= 0

    def bad_schema(_payload):
        return {"answers": {"importance": {"score": "huge", "confidence": "high"},
                            "kind": {"choice": 12345}}}
    d2 = decide_memory("another memory", caller=bad_schema)
    assert d2["retain"] is True and d2["kind"] in ("thought", "fact", "lesson")


def test_jev_default_off_even_with_caller(monkeypatch):
    monkeypatch.setitem(config, "jev_enabled", False)
    called = []
    def caller(p):
        called.append(p)
        return {"answers": {"importance": {"score": 8, "confidence": 0.9},
                            "kind": {"choice": "fact"}}}
    d = decide_memory("text", state="s", caller=caller)
    assert d["provider"] == "lexical"
    assert called == []  # no remote call


def test_jev_opt_in_uses_documented_endpoint(monkeypatch):
    monkeypatch.setitem(config, "jev_enabled", True)
    monkeypatch.setitem(config, "free_only", False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    seen = {}
    def caller(payload):
        seen.update(payload)
        assert payload["model"] == "typesafe/jev-1.13"
        assert set(payload["questions"]) == {"importance", "kind"}
        assert payload["questions"]["importance"]["type"] == "score"
        assert payload["questions"]["kind"]["type"] == "choice"
        return {"answers": {"importance": {"score": 7, "confidence": 0.8},
                            "kind": {"choice": "lesson"}}}
    d = decide_memory("lesson learned about kelp", state="state", caller=caller)
    assert d["provider"] == "jev"
    assert d["importance"] == 7 and d["kind"] == "lesson"
    assert DECISIONS_ENDPOINT == "https://openrouter.ai/api/alpha/decisions"
    assert DECISIONS_MODEL == "typesafe/jev-1.13"
    assert "confidence" in d and "latency_ms" in d
    # question limit + state cap
    p = build_decision_payload("x" * 100000)
    assert len(p["questions"]) <= 20
    assert len(p["state"]) <= 6000


def test_idle_reflect_rules_no_router():
    assert should_idle_reflect(100000) is True
    assert should_idle_reflect(0.0) is False
    assert not hasattr(decisions, "ModelRouter")


def test_no_delete_api_memories_kept():
    assert not hasattr(ResearchStore, "delete")
    assert not hasattr(decisions, "delete_memory")
