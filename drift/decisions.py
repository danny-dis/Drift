"""Optional typed judgments. Storage, budgets and owner policy remain authoritative."""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import uuid
from collections import deque
from typing import Any, Callable, Protocol

from drift.config import config
from drift.research import ResearchStore

logger = logging.getLogger("drift.decisions")
DECISIONS_ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DECISIONS_MODEL = "typesafe/jev-1.13"
MAX_QUESTIONS = 20
MAX_STATE_CHARS = 6000
SCHEMA_VERSION = "1"


class DecisionProvider(Protocol):
    def decide(self, state: dict | str, questions: list[dict]) -> dict: ...


_KIND_KEYWORDS = {
    "lesson": ("learned", "lesson", "mistake", "went wrong", "retrospective"),
    "fact": ("fact:", "is ", "are ", "measured", "version", "located at"),
    "thought": ("think", "wonder", "maybe", "idea", "consider"),
}


def _lex_kind(text: str) -> str:
    return next((kind for kind, cues in _KIND_KEYWORDS.items()
                 if any(cue in text.lower() for cue in cues)), "thought")


def _lex_importance(text: str) -> int:
    score = 2 + min(3, len(text) // 250)
    if any(cue in text.lower() for cue in ("error", "fail", "decision", "fact:", "learned", "important")):
        score += 2
    return max(0, min(9, score + int("?" in text)))


def _redact(text: str) -> str:
    text = re.sub(r'''(?i)((?:api[_ -]?key|token|password|secret)["']?\s*[:=]\s*["']?)[^\s,;"'}]+''',
                  r"\1[REDACTED]", text)
    patterns = (
        r"(?i)\bBearer\s+\S+|\bsk-[a-zA-Z0-9_-]{12,}",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----",
        # Conservatively remove unlabeled 40-character secret-key-shaped strings.
        r"(?<![A-Za-z0-9+/])(?=[A-Za-z0-9+/]{40}(?![A-Za-z0-9+/]))(?=[A-Za-z0-9+/]*[A-Za-z])(?=[A-Za-z0-9+/]*[0-9+/])[A-Za-z0-9+/]{40}",
    )
    for pattern in patterns:
        text = re.sub(pattern, "[REDACTED]", text)
    return text


def _safe_state(state: dict | str, settings: dict) -> dict | str:
    limit = max(2, min(int(settings.get("max_state_chars", settings.get("decision_max_state_chars", MAX_STATE_CHARS))), MAX_STATE_CHARS))
    def clean(value, depth=0):
        if depth > 5:
            return None
        if isinstance(value, dict):
            return {str(k): clean(v, depth + 1) for k, v in list(value.items())[:20]
                    if not re.search(r"key|token|password|secret|credential", str(k), re.I)}
        if isinstance(value, list):
            return [clean(v, depth + 1) for v in value[:20]]
        if isinstance(value, str):
            return _redact(value)[:limit]
        if value is None or isinstance(value, bool) or isinstance(value, (int, float)) and math.isfinite(value):
            return value
        return None
    if isinstance(state, str):
        return _redact(state)[:limit]
    allow = settings.get("allowed_state_fields", settings.get("decision_allowed_state_fields",
                ["text", "content", "kind", "scope", "importance", "timestamp", "candidates", "query"]))
    out = {}
    for key, value in clean(state).items():
        if key not in allow:
            continue
        trial = {**out, key: value}
        if len(json.dumps(trial, ensure_ascii=False)) <= limit:
            out = trial
        elif isinstance(value, str):
            while value and len(json.dumps({**out, key: value}, ensure_ascii=False)) > limit:
                value = value[:max(0, len(value) - max(1, len(json.dumps({**out, key: value}, ensure_ascii=False)) - limit))]
            if value:
                out[key] = value
    return out


def _valid_value(question: dict, value: Any) -> bool:
    kind = question.get("type")
    if kind == "score":
        bounds = (question.get("min"), question.get("max"))
        return (all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in bounds)
                and isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and bounds[0] <= value <= bounds[1])
    if kind == "choice":
        return isinstance(value, str) and value in question.get("options", [])
    return kind == "boolean" and isinstance(value, bool)


def _usage(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if k in ("input_tokens", "output_tokens", "prompt_tokens", "completion_tokens", "total_tokens", "cost")
            and isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0}


class DecisionService:
    """Provider-neutral boundary. Low-confidence/error output falls back, never deletes."""
    def __init__(self, settings=None, provider=None, llm_scorer=None, budget_root=None):
        self.settings = dict(config if settings is None else settings)
        if provider is None and self.settings.get("jev_enabled", False):
            self.settings.update(decision_models_enabled=True, decision_remote_opt_in=True, decision_provider="jev")
        self.provider = provider
        self.llm_scorer = llm_scorer
        self.budget_root = budget_root
        if provider is None and self.settings.get("decision_provider") == "jev":
            self.provider = _JevAdapter(lambda payload: _request_decisions(payload, budget_root),
                                        self.settings.get("decision_model", DECISIONS_MODEL))

    def decide(self, state: dict | str, questions: list[dict]) -> dict:
        if not isinstance(questions, list) or len(questions) > MAX_QUESTIONS or not all(isinstance(q, dict) for q in questions):
            raise ValueError(f"questions must be a list of at most {MAX_QUESTIONS} objects")
        ids = [q.get("id") for q in questions]
        if any(not isinstance(i, str) or not i or len(i) > 120 for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("question ids must be unique nonempty strings")
        for q in questions:
            if "default" not in q or not _valid_value(q, q["default"]):
                raise ValueError(f"invalid typed default for {q['id']}")
        started = time.monotonic()
        answers = {q["id"]: {"value": q["default"], "confidence": None} for q in questions}
        result = {"answers": answers, "provider": "deterministic", "model": None,
                  "decision_id": str(uuid.uuid4()), "schema_version": SCHEMA_VERSION,
                  "usage": {}, "fallback": None, "status": "default"}
        enabled = bool(self.settings.get("decision_models_enabled", self.settings.get("enabled", False)))
        provider = self.provider
        if enabled and provider is not None and questions:
            remote = bool(getattr(provider, "remote", False))
            permitted = not remote or (not self.settings.get("free_only", True)
                and not self.settings.get("local_only", self.settings.get("decision_local_only", False))
                and self.settings.get("remote_opt_in", self.settings.get("decision_remote_opt_in", False)))
            if permitted:
                budget = None
                reserved = False
                try:
                    if self.budget_root and not getattr(provider, "budget_managed", False):
                        from drift.providers import CallBudget
                        budget = CallBudget(self.budget_root)
                        budget.reserve()
                        reserved = True
                    raw = provider.decide(_safe_state(state, self.settings), questions)
                    validated = {}
                    for q in questions:
                        item = raw.get("answers", {}).get(q["id"], {})
                        value, confidence = item.get("value"), item.get("confidence")
                        if not _valid_value(q, value):
                            raise ValueError("invalid answer value")
                        if confidence is not None:
                            if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                    or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                                raise ValueError("invalid answer confidence")
                            if confidence < float(self.settings.get("decision_min_confidence", .60)):
                                raise ValueError("low confidence")
                        validated[q["id"]] = {"value": value, "confidence": confidence}
                    result.update(answers=validated, provider=str(raw.get("provider") or type(provider).__name__)[:120],
                                  model=str(raw.get("model"))[:120] if raw.get("model") else None,
                                  usage=_usage(raw.get("usage")), status="ok")
                    if budget:
                        budget.record_call(True, result["usage"].get("input_tokens", result["usage"].get("prompt_tokens", 0)),
                                           result["usage"].get("output_tokens", result["usage"].get("completion_tokens", 0)),
                                           reserved=True, reported=bool(result["usage"]))
                except Exception as exc:
                    result.update(answers=answers, status="fallback", fallback="default after " + type(exc).__name__)
                    if budget and reserved:
                        budget.record_call(False, reserved=True)
            else:
                result.update(status="fallback", fallback="remote provider blocked by privacy/free-only policy")
        elif enabled:
            result.update(status="fallback", fallback="decision provider unavailable")
        if result["status"] == "fallback" and self.llm_scorer is not None and self.settings.get("decisions_llm_fallback", False):
            # An injected scorer must obey the same privacy boundary and configured admission.
            if not self.settings.get("local_only", self.settings.get("decision_local_only", False)):
                budget = None
                reserved = False
                try:
                    if self.budget_root:
                        from drift.providers import CallBudget
                        budget = CallBudget(self.budget_root)
                        budget.reserve()
                        reserved = True
                    scored = self.llm_scorer(_safe_state(state, self.settings), questions)
                    if not all(q["id"] in scored and _valid_value(q, scored[q["id"]]) for q in questions):
                        raise ValueError("invalid scorer result")
                    result.update(answers={q["id"]: {"value": scored[q["id"]], "confidence": None} for q in questions},
                                  provider="llm_scorer", status="ok", fallback="llm after provider/default")
                    if budget:
                        budget.record_call(True, reserved=True, reported=False)
                except Exception:
                    if budget and reserved:
                        budget.record_call(False, reserved=True)
        result["latency_ms"] = int((time.monotonic() - started) * 1000)
        self._record(result, questions)
        return result

    def _record(self, result: dict, questions: list[dict]) -> None:
        if not self.budget_root:
            return
        try:
            os.makedirs(self.budget_root, exist_ok=True)
            telemetry = {k: result[k] for k in ("provider", "model", "decision_id", "schema_version", "latency_ms", "usage", "fallback", "status")}
            telemetry["questions"] = [{"id": q["id"], "type": q["type"],
                                      "confidence": result["answers"][q["id"]]["confidence"]} for q in questions]
            with open(os.path.join(self.budget_root, "decisions.jsonl"), "a", encoding="utf-8") as stream:
                stream.write(json.dumps(telemetry, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Decision telemetry unavailable")


class _JevAdapter:
    remote = True
    budget_managed = True
    def __init__(self, caller, model=DECISIONS_MODEL):
        self.caller, self.model = caller, model
    def decide(self, state, questions):
        raw = self.caller(build_decision_payload(json.dumps(state, ensure_ascii=False), questions, self.model))
        mapped = {}
        for q in questions:
            item = raw.get("answers", {}).get(q["id"], {})
            value = item.get("value", item.get("score", item.get("option", item.get("choice"))))
            mapped[q["id"]] = {"value": value, "confidence": item.get("confidence")}
        return {"answers": mapped, "provider": "jev", "model": raw.get("model", self.model), "usage": raw.get("usage", {})}


def build_decision_payload(state: str, questions: list[dict] | None = None, model: str = DECISIONS_MODEL) -> dict:
    if questions is None:
        questions = [{"id": "importance", "type": "score", "min": 0, "max": 9},
                     {"id": "kind", "type": "choice", "options": list(_KIND_KEYWORDS)}]
    if len(questions) > MAX_QUESTIONS:
        raise ValueError("too many decision questions")
    typed = {}
    for q in questions:
        entry = {"type": q["type"], "instructions": str(q.get("instructions", q["id"]))[:500]}
        if q["type"] == "choice":
            entry["criteria"] = {option: option for option in q["options"]}
        if q["type"] == "score":
            entry["instructions"] += f" Range {q['min']}..{q['max']}."
        typed[q["id"]] = entry
    return {"model": model, "state": (state or "")[:MAX_STATE_CHARS], "questions": typed}


def _request_decisions(payload: dict[str, Any], budget_root: str | None) -> dict[str, Any]:
    import urllib.request
    from drift.providers import CallBudget
    if config.get("free_only", True):
        raise RuntimeError("remote decisions disabled in free-only mode")
    budget = CallBudget(budget_root or str(config.get("environment_path", "environment")))
    budget.reserve()
    try:
        request = urllib.request.Request(DECISIONS_ENDPOINT, data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read(100000))
        usage = _usage(result.get("usage"))
        budget.record_call(True, usage.get("prompt_tokens", usage.get("input_tokens", 0)),
                           usage.get("completion_tokens", usage.get("output_tokens", 0)), reserved=True, reported=bool(usage))
        return result
    except Exception:
        budget.record_call(False, reserved=True)
        raise


def decide_memory(text: str, state: str = "", caller: Callable[[dict], dict] | None = None,
                  budget_root: str | None = None, service: DecisionService | None = None,
                  candidates: list[dict] | None = None) -> dict:
    """Batch optional judgments, never suppress an append or alter explicit memory kind."""
    score, kind = _lex_importance(text), _lex_kind(text)
    questions = [{"id": "importance", "type": "score", "min": 0, "max": 9, "default": score},
                 {"id": "kind", "type": "choice", "options": list(_KIND_KEYWORDS), "default": kind}]
    if config.get("decision_memory_advisory_enabled", False):
        questions += [{"id": "retention", "type": "choice", "options": ["normal", "long_term", "permanent"], "default": "normal"},
                      {"id": "novelty", "type": "choice", "options": ["unassessed", "duplicate", "related", "new"], "default": "unassessed"},
                      {"id": "contradiction", "type": "boolean", "default": False},
                      {"id": "promotion", "type": "boolean", "default": False},
                      {"id": "reflection", "type": "boolean", "default": False}]
    if service is None:
        settings = dict(config)
        if settings.get("jev_enabled", False):
            settings.update(decision_models_enabled=True, decision_remote_opt_in=True)
            provider = _JevAdapter(caller or (lambda payload: _request_decisions(payload, budget_root)),
                                   settings.get("decision_model", DECISIONS_MODEL))
        else:
            provider = None
        service = DecisionService(settings, provider, budget_root=budget_root)
    result = service.decide({"text": text, "content": state, "candidates": candidates or []}, questions)
    values = {key: answer["value"] for key, answer in result["answers"].items()}
    out = {key: result[key] for key in ("model", "decision_id", "schema_version", "status", "usage", "fallback", "latency_ms")}
    out.update(importance=values["importance"], importance_display=int(round(values["importance"])) + 1,
               kind=values["kind"], retain=True, provider="lexical" if result["provider"] == "deterministic" else result["provider"],
               confidence=result["answers"]["importance"]["confidence"],
               retention=values.get("retention", "long_term" if score >= 7 else "normal"),
               novelty=values.get("novelty", "unassessed"), promotion_candidate=values.get("promotion", False),
               reflection_candidate=values.get("reflection", False),
               contradiction_candidates=[c["id"] for c in candidates or [] if "id" in c] if values.get("contradiction", False) else [])
    return out


def get_decision_summary(budget_root: str | None) -> dict:
    """Bounded tail-window telemetry, never memory state or provider inputs."""
    records = deque(maxlen=1000)
    truncated = False
    if budget_root:
        try:
            with open(os.path.join(budget_root, "decisions.jsonl"), "rb") as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 1_048_576))
                if size > 1_048_576:
                    stream.readline()
                    truncated = True
                for line in stream:
                    if len(line) > 8192:
                        continue
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict):
                            if len(records) == records.maxlen:
                                truncated = True
                            records.append(item)
                    except (ValueError, TypeError):
                        continue
        except OSError:
            pass
    providers = {}
    latency = []
    for item in records:
        name = str(item.get("provider") or "unknown")[:120]
        providers[name] = providers.get(name, 0) + 1
        value = item.get("latency_ms")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            latency.append(value)
    return {"count": len(records), "fallbacks": sum(r.get("status") == "fallback" for r in records),
            "failures": sum(r.get("status") in ("error", "failed") for r in records), "providers": providers,
            "mean_latency_ms": sum(latency) / len(latency) if latency else None,
            "window": "last 1000 valid entries, within a 1 MiB tail", "truncated": truncated}


def should_idle_reflect(importance_sum: float) -> bool:
    return float(importance_sum) >= float(config.get("reflection_threshold", 50))
