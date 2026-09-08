"""Capability interface and provider routing for Drift (Phase 4).

Drift requests capabilities (classify_idea, research, verify_claims, …)
rather than hard‑coding a particular model. A lightweight router picks the
cheapest provider that can handle the task and escalates when needed.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from drift.config import config

logger = logging.getLogger("drift.capabilities")

# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

# Each capability lists candidate providers in preference order.
# ``local`` means on‑device deterministic code (no model call).
# ``cheap`` means a low‑cost API model; ``strong`` means a more expensive one.

CAPABILITIES: dict[str, dict[str, Any]] = {
    "classify_idea": {
        "description": "Assign an idea to PROJECT / RESEARCH / PARKED",
        "cheap": ["rule_based", "llm"],
        "default": "rule_based",
    },
    "extract_concepts": {
        "description": "Pull key concepts out of a piece of text",
        "cheap": ["rule_based"],
        "default": "rule_based",
    },
    "embed": {
        "description": "Turn text into a numeric vector",
        "cheap": ["openai", "ollama", "local"],
        "default": "openai",
    },
    "match_project": {
        "description": "Score how well an idea matches existing projects",
        "cheap": ["rule_based", "llm"],
        "default": "rule_based",
    },
    "analyze_diff": {
        "description": "Summarise a code diff and assess impact",
        "cheap": ["llm"],
        "default": "llm",
    },
    "research": {
        "description": "Investigate a topic and produce a written report",
        "cheap": ["llm"],
        "default": "llm",
    },
    "verify_claims": {
        "description": "Check a claim against evidence",
        "cheap": ["llm"],
        "default": "llm",
    },
    "compare_alternatives": {
        "description": "Compare two or more options side‑by‑side",
        "cheap": ["llm"],
        "default": "llm",
    },
    "challenge_assumption": {
        "description": "Find weak points in a belief or plan",
        "cheap": ["llm"],
        "default": "llm",
    },
    "synthesize": {
        "description": "Combine several findings into a coherent summary",
        "cheap": ["llm"],
        "default": "llm",
    },
    "summarize": {
        "description": "Condense a long text into key points",
        "cheap": ["llm"],
        "default": "llm",
    },
}


def list_capabilities() -> dict[str, str]:
    """Return {name: description} for every registered capability."""
    return {name: meta["description"] for name, meta in CAPABILITIES.items()}


def is_capability(name: str) -> bool:
    return name in CAPABILITIES


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

@dataclass
class Provider:
    """A model/provider that can fulfil capabilities."""
    name: str
    model: str
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    cost_per_1k_tokens: float = 0.002  # rough USD; used only for budget maths
    capabilities: set[str] = field(default_factory=lambda: set(CAPABILITIES.keys()))
    is_local: bool = False

    def is_available(self) -> bool:
        """True if credentials for this provider exist."""
        if self.is_local:
            return True
        return bool(os.environ.get(self.api_key_env))


# Ordered list – first available provider wins.
PROVIDERS: list[Provider] = [
    Provider(
        name="local",
        model="none",
        cost_per_1k_tokens=0.0,
        capabilities={"classify_idea", "extract_concepts", "match_project", "embed"},
        is_local=True,
    ),
    Provider(
        name="ollama",
        model="llama3.2",
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",
        cost_per_1k_tokens=0.0,
        capabilities={"embed", "summarize", "classify_idea", "extract_concepts"},
    ),
    Provider(
        name="openrouter",
        model="google/gemini-2.0-flash-001",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        cost_per_1k_tokens=0.00025,
    ),
    Provider(
        name="openai",
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        cost_per_1k_tokens=0.001,
    ),
    Provider(
        name="openai-strong",
        model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        cost_per_1k_tokens=0.01,
        capabilities={"analyze_diff", "research", "verify_claims",
                      "compare_alternatives", "challenge_assumption",
                      "synthesize", "summarize"},
    ),
]


def route_capability(capability: str, allow_strong: bool = False) -> Provider:
    """Return the cheapest available provider for *capability*.

    If *allow_strong* is True the search includes high‑cost providers.
    Raises RuntimeError if nothing can fulfil the capability.
    """
    if not is_capability(capability):
        raise ValueError(f"unknown capability: {capability}")

    candidates = []
    for p in PROVIDERS:
        if capability not in p.capabilities:
            continue
        if not p.is_available():
            continue
        if p.name == "openai-strong" and not allow_strong:
            continue
        candidates.append(p)

    if not candidates:
        raise RuntimeError(f"no available provider for {capability}")

    candidates.sort(key=lambda p: p.cost_per_1k_tokens)
    winner = candidates[0]
    logger.info(
        "route_capability %s -> %s (%s) [cost %.4f / 1k tok]",
        capability, winner.name, winner.model, winner.cost_per_1k_tokens,
    )
    return winner


# ---------------------------------------------------------------------------
# Escalation logic
# ---------------------------------------------------------------------------

_ESCALATION_REASONS = {
    "low_confidence",
    "conflicting_evidence",
    "high_impact",
    "security_sensitive",
    "complex_reasoning",
    "repeated_failure",
    "owner_request",
}


def should_escalate(reason: str) -> bool:
    """True if *reason* justifies routing to a stronger (more expensive) model."""
    return reason in _ESCALATION_REASONS


def escalate(capability: str) -> Provider:
    """Return a stronger provider for *capability*, bypassing cost ordering."""
    return route_capability(capability, allow_strong=True)


# ---------------------------------------------------------------------------
# Telemetry – usage / cost tracking
# ---------------------------------------------------------------------------

@dataclass
class UsageEvent:
    """Record of one model call."""
    capability: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    success: bool
    reason: str = ""  # escalation reason, if any
    timestamp: float = field(default_factory=time.time)


class UsageTracker:
    """Append‑only telemetry for model usage."""

    def __init__(self) -> None:
        self._events: list[UsageEvent] = []

    def record(self, event: UsageEvent) -> None:
        self._events.append(event)

    def total_cost(self) -> float:
        return sum(e.estimated_cost for e in self._events)

    def cost_by_capability(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self._events:
            out[e.capability] = out.get(e.capability, 0.0) + e.estimated_cost
        return out

    def cost_by_provider(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for e in self._events:
            out[e.provider] = out.get(e.provider, 0.0) + e.estimated_cost
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "total_calls": len(self._events),
            "total_cost": self.total_cost(),
            "successful": sum(1 for e in self._events if e.success),
            "failed": sum(1 for e in self._events if not e.success),
            "by_capability": self.cost_by_capability(),
            "by_provider": self.cost_by_provider(),
        }


# Global tracker
USAGE = UsageTracker()
