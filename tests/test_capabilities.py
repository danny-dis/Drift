"""Tests for drift/capabilities.py — capability routing and telemetry."""
import os
from unittest.mock import patch

import pytest

from drift.capabilities import (
    CAPABILITIES,
    PROVIDERS,
    UsageEvent,
    UsageTracker,
    escalate,
    is_capability,
    list_capabilities,
    route_capability,
    should_escalate,
)


class TestCapabilities:
    def test_all_capabilities_have_description(self):
        for name, meta in CAPABILITIES.items():
            assert "description" in meta
            assert "cheap" in meta
            assert "default" in meta

    def test_is_capability(self):
        assert is_capability("classify_idea")
        assert is_capability("research")
        assert not is_capability("nonexistent")

    def test_list_capabilities(self):
        caps = list_capabilities()
        assert "classify_idea" in caps
        assert "research" in caps


class TestRouting:
    def test_routes_to_local_when_available(self):
        # local provider is always available and cheapest
        provider = route_capability("classify_idea")
        assert provider.name == "local"

    def test_routes_to_cheapest_available(self):
        # With no env vars set, only "local" is available for most caps
        provider = route_capability("extract_concepts")
        assert provider.name == "local"

    def test_unknown_capability_raises(self):
        with pytest.raises(ValueError):
            route_capability("nonexistent")

    def test_escalate_includes_strong(self):
        # With no env vars, escalate falls back to local if available
        provider = escalate("classify_idea")
        assert provider is not None


class TestEscalation:
    def test_valid_reasons(self):
        assert should_escalate("low_confidence")
        assert should_escalate("security_sensitive")
        assert should_escalate("owner_request")

    def test_invalid_reason(self):
        assert not should_escalate("random_reason")


class TestUsageTracker:
    def test_empty(self):
        tracker = UsageTracker()
        assert tracker.total_cost() == 0.0
        assert tracker.summary()["total_calls"] == 0

    def test_record_and_total(self):
        tracker = UsageTracker()
        tracker.record(UsageEvent(
            capability="research",
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01,
            success=True,
        ))
        tracker.record(UsageEvent(
            capability="research",
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=200,
            output_tokens=100,
            estimated_cost=0.02,
            success=True,
        ))
        assert tracker.total_cost() == 0.03
        assert tracker.summary()["total_calls"] == 2

    def test_cost_by_capability(self):
        tracker = UsageTracker()
        tracker.record(UsageEvent(
            capability="research", provider="openai", model="gpt-4o-mini",
            input_tokens=100, output_tokens=50, estimated_cost=0.01, success=True,
        ))
        tracker.record(UsageEvent(
            capability="summarize", provider="openai", model="gpt-4o-mini",
            input_tokens=100, output_tokens=50, estimated_cost=0.005, success=True,
        ))
        by_cap = tracker.cost_by_capability()
        assert by_cap["research"] == 0.01
        assert by_cap["summarize"] == 0.005

    def test_cost_by_provider(self):
        tracker = UsageTracker()
        tracker.record(UsageEvent(
            capability="research", provider="openai", model="gpt-4o-mini",
            input_tokens=100, output_tokens=50, estimated_cost=0.01, success=True,
        ))
        tracker.record(UsageEvent(
            capability="research", provider="openrouter", model="gemini",
            input_tokens=100, output_tokens=50, estimated_cost=0.005, success=True,
        ))
        by_prov = tracker.cost_by_provider()
        assert by_prov["openai"] == 0.01
        assert by_prov["openrouter"] == 0.005

    def test_summary(self):
        tracker = UsageTracker()
        tracker.record(UsageEvent(
            capability="research", provider="openai", model="gpt-4o-mini",
            input_tokens=100, output_tokens=50, estimated_cost=0.01, success=True,
        ))
        tracker.record(UsageEvent(
            capability="research", provider="openai", model="gpt-4o-mini",
            input_tokens=100, output_tokens=50, estimated_cost=0.01, success=False,
        ))
        summary = tracker.summary()
        assert summary["total_calls"] == 2
        assert summary["successful"] == 1
        assert summary["failed"] == 1
