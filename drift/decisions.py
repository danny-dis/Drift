"""Small deterministic memory decisions + research sessions (PR5 core).

YAGNI: plain small functions, stdlib only, no plugin framework, no router.
- Deterministic decisions by default; legacy LLM fallback only with
  explicit opt-in (config decisions_llm_fallback).
- JEV remote (OpenRouter decisions endpoint) default OFF; requires
  explicit opt-in (config jev_enabled) + credential; failures never
  lose the memory.
- One batched decision call returns importance + kind + retention
  metadata; never deletes stored memories.
- Question limit 20; state capped before send.
- No remote call in tests (injectable caller).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable

from drift.config import config
from drift.research import ResearchStore

logger = logging.getLogger("drift.decisions")

DECISIONS_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DECISIONS_MODEL = "typesafe/jev-1.13"
MAX_QUESTIONS = 20
MAX_STATE_CHARS = 6000

_KIND_KEYWORDS = {
    "lesson": ("learned", "lesson", "mistake", "went wrong", "retrospective"),
    "fact": ("fact:", "is ", "are ", "measured", "version", "located at"),
    "thought": ("think", "wonder", "maybe", "idea", "consider"),
}


def _lex_kind(text: str) -> str:
    c = text.lower()
    for kind, cues in _KIND_KEYWORDS.items():
        if any(k in c for k in cues):
            return kind
    return "thought"


def _lex_importance(text: str) -> int:
    """Deterministic 0..9 zero-indexed score (maps to 1..10 display)."""
    c = text.lower()
    score = 2 + min(3, len(text) // 250)
    for cue in ("error", "fail", "decision", "fact:", "learned", "important"):
        if cue in c:
            score += 2
            break
    if "?" in text:
        score += 1
    return max(0, min(9, score))


def build_decision_payload(state: str) -> dict:
    """Build the single batched JEV payload. Caps state, 2 questions max."""
    capped = (state or "")[:MAX_STATE_CHARS]
    return {
        "model": DECISIONS_MODEL,
        "state": capped,
        "questions": {
            "importance": {
                "type": "score",
                "instructions": "Rate lasting value of this memory 0..9.",
                "criteria": ["transient noise", "routine detail", "minor observation", "useful context",
                             "reusable insight", "project decision", "important lesson", "lasting constraint",
                             "critical evidence", "essential long-term knowledge"],
            },
            "kind": {
                "type": "choice",
                "instructions": "Classify the memory.",
                "criteria": {
                    "thought": "passing thought/pondering",
                    "fact": "durable verifiable fact",
                    "lesson": "learned lesson to keep",
                },
            },
        },
    }


def _request_decisions(payload: dict[str, Any], budget_root: str | None) -> dict[str, Any]:
    """Optional documented Alpha endpoint. Never contacted in free-only mode."""
    import urllib.request
    from drift.providers import CallBudget
    if config.get("free_only", True):
        raise RuntimeError("remote decisions disabled in free-only mode")
    budget = CallBudget(budget_root or str(config.get("environment_path", "environment")))
    budget.reserve()  # raises on denial; successful reservation returns None
    request = urllib.request.Request(DECISIONS_ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read(100000))
        usage = result.get("usage", {})
        budget.record_call(True, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), reserved=True)
        return result
    except Exception:
        budget.record_call(False, reserved=True)
        raise


def decide_memory(text: str, state: str = "", caller: Callable[[dict], dict] | None = None,
                  budget_root: str | None = None) -> dict:
    """One local decision by default; optional typed batch, never delete data."""
    score = _lex_importance(text)
    out = {"importance": score, "importance_display": score + 1, "kind": _lex_kind(text),
           "retain": True, "provider": "lexical", "confidence": None,
           "novelty": "duplicate" if text and text in state else "new",
           "retention": "long_term" if score >= 7 else "normal",
           "fallback": None, "latency_ms": 0}
    if not config.get("jev_enabled", False):
        return out
    if config.get("free_only", True):
        out["fallback"] = "free-only: remote typed decisions disabled"
        return out
    if not os.environ.get("OPENROUTER_API_KEY"):
        out["fallback"] = "no-credential"
        return out
    started = time.monotonic()
    try:
        payload = build_decision_payload(text + "\nPrior state: " + state)
        raw = (caller or (lambda p: _request_decisions(p, budget_root)))(payload)
        answers = raw["answers"]
        imp, kind = answers["importance"], answers["kind"]
        value = imp["score"]
        category = kind.get("option", kind.get("choice"))
        confidence = imp.get("confidence")
        if (not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 9
                or category not in _KIND_KEYWORDS
                or confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1)):
            raise ValueError("invalid typed decision")
        out.update(importance=value, importance_display=int(round(value)) + 1,
                   kind=category, provider="jev", confidence=confidence)
    except Exception as error:
        logger.warning("Typed decisions failed (%s); preserving memory with local metadata", type(error).__name__)
        out["fallback"] = "lexical"
    finally:
        out["latency_ms"] = int((time.monotonic() - started) * 1000)
    return out


def should_idle_reflect(importance_sum: float) -> bool:
    """Rule-based idle/reflect gate. No model router."""
    try:
        threshold = float(config.get("reflection_threshold", 50))
    except (TypeError, ValueError):
        threshold = 50.0
    return float(importance_sum) >= threshold
