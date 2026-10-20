"""Research + challenge engine for Drift (Phase 5).

Handles research workflows: extracting evidence from text, comparing
sources, verifying claims, generating alternatives, and challenging
assumptions. All logic is deterministic and cheap — no model calls
except where explicitly noted.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse

from drift.config import config

logger = logging.getLogger("drift.research")


# ---------------------------------------------------------------------------
# Research modes
# ---------------------------------------------------------------------------

RESEARCH_MODES = {
    "deep_dive": {
        "description": "Thorough investigation of a single topic",
        "max_searches": 8,
        "max_sources": 5,
        "synthesis_required": True,
    },
    "broad_scan": {
        "description": "Wide survey of many sources on a topic",
        "max_searches": 5,
        "max_sources": 10,
        "synthesis_required": False,
    },
    "targeted_lookup": {
        "description": "Quick answer to a specific question",
        "max_searches": 2,
        "max_sources": 3,
        "synthesis_required": False,
    },
}


def get_mode(mode: str) -> dict[str, Any]:
    """Return config for a research mode."""
    if mode not in RESEARCH_MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {list(RESEARCH_MODES)}")
    return RESEARCH_MODES[mode]


# ---------------------------------------------------------------------------
# Evidence extraction
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """A single piece of extracted evidence."""
    text: str
    source: str = ""
    confidence: float = 0.5
    kind: str = "observation"  # fact, observation, hypothesis, opinion
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source": self.source,
            "confidence": self.confidence,
            "kind": self.kind,
            "timestamp": self.timestamp,
        }


# Claim indicators — words that often precede a factual claim
_CLAIM_INDICATORS = [
    r"\b(studies show|research shows|evidence suggests|data indicates|research indicates)\b",
    r"\b(it is known|it has been shown|experts say|scientists found)\b",
    r"\b(according to|reported by|published in)\b",
    r"(?:\d+%|\d+ percent|statistics show|survey found)",
]

# Opinion markers
_OPINION_INDICATORS = [
    r"\b(I think|I believe|in my opinion|it seems|appears to)\b",
    r"\b(should|must|ought to|recommended|advised)\b",
]


def extract_claims(text: str) -> list[str]:
    """Extract factual-sounding statements from text.

    Looks for sentences that contain claim indicators (studies show,
    X% of, according to) or that make definitive assertions.
    """
    if not text.strip():
        return []

    sentences = re.split(r"[.!?]+\s+", text)
    claims = []

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            continue
        for pattern in _CLAIM_INDICATORS:
            if re.search(pattern, sentence, re.IGNORECASE):
                claims.append(sentence)
                break

    return claims


def extract_evidence(text: str, source: str = "") -> list[Evidence]:
    """Extract evidence items from a text.

    Returns a list of Evidence objects with kind and confidence.
    """
    if not text.strip():
        return []

    claims = extract_claims(text)
    evidence = []

    for claim in claims:
        kind = "fact"
        confidence = 0.6

        # Downgrade to "opinion" if opinion markers are present
        for pattern in _OPINION_INDICATORS:
            if re.search(pattern, claim, re.IGNORECASE):
                kind = "opinion"
                confidence = 0.3
                break

        evidence.append(Evidence(
            text=claim,
            source=source,
            confidence=confidence,
            kind=kind,
        ))

    return evidence


# ---------------------------------------------------------------------------
# Source comparison
# ---------------------------------------------------------------------------

@dataclass
class SourceComparison:
    """Result of comparing two sources on the same claim."""
    claim: str
    source_a: str
    source_b: str
    agreement: float  # 0.0-1.0
    details: str = ""


def compare_sources(evidence_a: Evidence, evidence_b: Evidence) -> SourceComparison:
    """Compare two pieces of evidence for agreement.

    Simple lexical overlap comparison. A real system would use embeddings.
    """
    text_a = evidence_a.text.lower()
    text_b = evidence_b.text.lower()

    # Tokenize
    tokens_a = set(re.findall(r"[a-z0-9]{3,}", text_a))
    tokens_b = set(re.findall(r"[a-z0-9]{3,}", text_b))

    if not tokens_a or not tokens_b:
        agreement = 0.0
    else:
        # Jaccard similarity
        agreement = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    details = ""
    if agreement >= 0.5:
        details = "Sources largely agree"
    elif agreement >= 0.3:
        details = "Sources partially agree"
    else:
        details = "Sources disagree or discuss different aspects"

    return SourceComparison(
        claim=evidence_a.text[:200],
        source_a=evidence_a.source,
        source_b=evidence_b.source,
        agreement=round(agreement, 3),
        details=details,
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Result of verifying a claim against evidence."""
    claim: str
    verdict: str  # "supported", "contradicted", "insufficient_evidence"
    confidence: float
    supporting: list[Evidence] = field(default_factory=list)
    contradicting: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "supporting": [e.to_dict() for e in self.supporting],
            "contradicting": [e.to_dict() for e in self.contradicting],
        }


def verify_claim(claim: str, evidence_list: list[Evidence]) -> VerificationResult:
    """Check whether a claim is supported by available evidence.

    Uses lexical overlap between claim and each evidence item.
    """
    if not evidence_list:
        return VerificationResult(
            claim=claim,
            verdict="insufficient_evidence",
            confidence=0.0,
        )

    claim_tokens = set(re.findall(r"[a-z0-9]{3,}", claim.lower()))

    supporting = []
    contradicting = []

    for ev in evidence_list:
        ev_tokens = set(re.findall(r"[a-z0-9]{3,}", ev.text.lower()))
        if not ev_tokens:
            continue
        overlap = len(claim_tokens & ev_tokens) / max(len(claim_tokens), 1)
        if overlap >= 0.4:
            supporting.append(ev)
        elif overlap < 0.2:
            contradicting.append(ev)

    if supporting and not contradicting:
        verdict = "supported"
        confidence = min(0.9, 0.5 + 0.1 * len(supporting))
    elif contradicting and not supporting:
        verdict = "contradicted"
        confidence = min(0.8, 0.4 + 0.1 * len(contradicting))
    elif supporting and contradicting:
        verdict = "insufficient_evidence"
        confidence = 0.3
    else:
        verdict = "insufficient_evidence"
        confidence = 0.1

    return VerificationResult(
        claim=claim,
        verdict=verdict,
        confidence=round(confidence, 3),
        supporting=supporting,
        contradicting=contradicting,
    )


# ---------------------------------------------------------------------------
# Alternatives
# ---------------------------------------------------------------------------

def generate_alternatives(
    claim: str,
    evidence_list: list[Evidence],
    max_alternatives: int = 3,
) -> list[str]:
    """Generate alternative explanations for a claim.

    Looks for evidence items that suggest different mechanisms,
    contexts, or interpretations.
    """
    if not evidence_list:
        return []

    alternatives = []
    seen_texts = set()

    # Use evidence items that don't directly support the claim
    claim_tokens = set(re.findall(r"[a-z0-9]{3,}", claim.lower()))

    for ev in evidence_list:
        ev_tokens = set(re.findall(r"[a-z0-9]{3,}", ev.text.lower()))
        if not ev_tokens:
            continue
        overlap = len(claim_tokens & ev_tokens) / max(len(claim_tokens), 1)
        if overlap < 0.3 and ev.text not in seen_texts:
            alternatives.append(ev.text)
            seen_texts.add(ev.text)
            if len(alternatives) >= max_alternatives:
                break

    return alternatives


# ---------------------------------------------------------------------------
# Challenge engine
# ---------------------------------------------------------------------------

@dataclass
class Challenge:
    """A challenge to an assumption or belief."""
    target: str
    challenge: str
    confidence: float
    kind: str = "assumption"  # assumption, gap, risk, contradiction


# Common assumption patterns
_ASSUMPTION_PATTERNS = [
    (r"\b(all|every|always|never|none)\b", "absolute_claim"),
    (r"\b(clearly|obviously|undoubtedly|certainly)\b", "unwarranted_certainty"),
    (r"\b(must|have to|need to|require)\b", "necessity_assumption"),
    (r"\b(better|best|worst|worse)\b", "value_judgment"),
    (r"\b(because|therefore|thus|hence)\b", "causal_assumption"),
]


def challenge_assumption(text: str) -> list[Challenge]:
    """Find and challenge assumptions in a text.

    Returns a list of Challenge objects with the issue found.
    """
    challenges = []
    sentences = re.split(r"[.!?]+\s+", text)

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 15:
            continue

        for pattern, kind in _ASSUMPTION_PATTERNS:
            if re.search(pattern, sentence, re.IGNORECASE):
                challenge_text = _generate_challenge(sentence, kind)
                if challenge_text:
                    challenges.append(Challenge(
                        target=sentence,
                        challenge=challenge_text,
                        confidence=0.6,
                        kind=kind,
                    ))

    return challenges


def _generate_challenge(sentence: str, kind: str) -> str:
    """Generate a challenge text based on the kind of assumption."""
    challenges = {
        "absolute_claim": f"Challenge: '{sentence[:80]}' uses absolute language. Are there really no exceptions?",
        "unwarranted_certainty": f"Challenge: '{sentence[:80]}' claims certainty. What evidence would change this?",
        "necessity_assumption": f"Challenge: '{sentence[:80]}' assumes necessity. Are there other ways to achieve the same outcome?",
        "value_judgment": f"Challenge: '{sentence[:80]}' makes a value judgment. Better/worse by whose criteria?",
        "causal_assumption": f"Challenge: '{sentence[:80]}' implies causation. Could there be other factors at play?",
    }
    return challenges.get(kind, "")


# ---------------------------------------------------------------------------
# Research orchestrator
# ---------------------------------------------------------------------------

@dataclass
class ResearchReport:
    """A structured research report."""
    topic: str
    mode: str
    findings: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    challenges: list[Challenge] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "mode": self.mode,
            "findings": self.findings,
            "evidence": [e.to_dict() for e in self.evidence],
            "challenges": [{"target": c.target, "challenge": c.challenge,
                           "confidence": c.confidence, "kind": c.kind}
                          for c in self.challenges],
            "alternatives": self.alternatives,
            "confidence": self.confidence,
        }


def synthesize_findings(
    topic: str,
    mode: str,
    evidence_list: list[Evidence],
    challenges: list[Challenge],
    alternatives: list[str],
) -> ResearchReport:
    """Synthesize evidence, challenges, and alternatives into a report."""
    # Extract findings from evidence
    findings = []
    for ev in evidence_list:
        if ev.confidence >= 0.5:
            prefix = "Fact" if ev.kind == "fact" else "Observation"
            findings.append(f"{prefix}: {ev.text}")

    # Overall confidence: average of evidence confidence, reduced by challenges
    if evidence_list:
        avg_confidence = sum(e.confidence for e in evidence_list) / len(evidence_list)
    else:
        avg_confidence = 0.3

    challenge_penalty = min(0.3, 0.1 * len(challenges))
    confidence = max(0.1, avg_confidence - challenge_penalty)

    return ResearchReport(
        topic=topic,
        mode=mode,
        findings=findings,
        evidence=evidence_list,
        challenges=challenges,
        alternatives=alternatives,
        confidence=round(confidence, 3),
    )


# ---------------------------------------------------------------------------
# ResearchStore — durable deterministic session store (PR3/4, stdlib only)
# ---------------------------------------------------------------------------
# Minimal contract:
#   ResearchStore(root)
#   start(query, task_id=None, project_id=None, strategy='targeted_lookup')
#   add_source(session_id, url, text)
#   finish(session_id, report)
#   get(session_id) / list()
# No network fetch here (Brain tools fetch). No lexical-overlap factual
# proof: verification flags mean "citations reference retained sources".

STRATEGIES = (
    "broad_scan",
    "deep_dive",
    "targeted_lookup",
    "experiment",
    "connect",
    "challenge",
)

SESSION_STATES = (
    "selecting",
    "researching",
    "verifying",
    "complete",
    "needs_review",
)

RESEARCH_PHASES = (
    "selecting",
    "researching",
    "synthesizing",
    "writing",
    "verifying",
    "publishing",
    "sleeping",
)
MAX_LINEAGE_ITEMS = 100
MAX_LINEAGE_DETAIL_CHARS = 4000
MAX_REPAIR_CONTEXT = 3

PROPOSAL_STATES = (
    "proposed",
    "accepted",
    "rejected",
    "implemented",
    "superseded",
)

PROPOSAL_TRANSITIONS = {
    "proposed": {"accepted", "rejected"},
    "accepted": {"implemented", "rejected", "superseded"},
    "rejected": {"proposed"},
    "implemented": {"superseded"},
    "superseded": set(),
}

MAX_SOURCES = 10
MAX_SOURCE_CHARS = 4000
MAX_REPORT_CHARS = 8000
MAX_REPAIRS = 2

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_HYP_RE = re.compile(
    r"\b(might|could|may|maybe|possibly|perhaps|likely|hypothes\w*)\b",
    re.IGNORECASE,
)
_NEG_CUES = frozenset({
    "not", "no", "never", "none", "neither", "nor", "n't",
    "fail", "fails", "failed", "false", "contradict", "disagree",
    "refute", "deny", "denies", "lack", "lacks", "without",
})
_STOPWORDS = frozenset({
    "what", "which", "that", "this", "with", "from", "compare",
    "versus", "evaluate", "does", "s", "and", "the", "for",
})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def _canonical_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("empty url")
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"bad url {url!r}")
    host = parts.hostname.lower()
    path = parts.path.rstrip("/") or ""
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    return urlunparse((parts.scheme.lower(), netloc, path, "", parts.query, ""))


def _tag_claim(text: str) -> str:
    """Tag a claim observation/hypothesis/opinion. Never a proof verdict."""
    if _HYP_RE.search(text):
        return "hypothesis"
    for pattern in _OPINION_INDICATORS:
        if re.search(pattern, text, re.IGNORECASE):
            return "opinion"
    return "observation"


def _is_significant(query: str) -> bool:
    words = re.findall(r"[A-Za-z0-9']+", query)
    q = query.lower()
    long_multi = len(words) >= 12 and ("?" in query or " and " in q)
    compare = (" vs " in q or "compare" in q or "evaluate" in q) and len(words) >= 8
    return bool(long_multi or compare)


def _keywords(query: str, limit: int = 4) -> list[str]:
    seen: list[str] = []
    for w in re.findall(r"[a-z0-9]{4,}", query.lower()):
        if w not in _STOPWORDS and w not in seen:
            seen.append(w)
        if len(seen) >= limit:
            break
    return seen


def _build_candidates(query: str) -> tuple[list[dict[str, Any]], list[str]]:
    if not _is_significant(query):
        return [], []
    kws = _keywords(query) or ["topic"]
    cands = [
        {"text": f"Candidate hypothesis: {' / '.join(kws[:2])} explains the observed pattern.", "support": 0.0},
        {"text": f"Candidate hypothesis: an alternative factor beyond {kws[0]} drives the outcome.", "support": 0.0},
    ]
    outline = [
        f"What evidence exists about: {query[:120]}?",
        "How do the retained sources compare on the key points?",
        "What remains uncertain or uncorroborated?",
    ]
    return cands, outline


_RESEARCH_LOCKS = {}


class ResearchStore:
    """Disk-backed research sessions. Atomic writes, lock-guarded updates."""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self._sessions = os.path.join(self.root, "sessions")
        self._reports = os.path.join(self.root, "research")
        from drift.research_lock import ResearchMutex
        self._lock = _RESEARCH_LOCKS.setdefault(self.root, ResearchMutex(self.root))
        os.makedirs(self._sessions, exist_ok=True)
        os.makedirs(self._reports, exist_ok=True)

    # -- internals ------------------------------------------------------
    def _check_id(self, session_id: str) -> str:
        if not isinstance(session_id, str) or not _ID_RE.match(session_id):
            raise ValueError(f"bad session id {session_id!r}")
        return session_id

    def _path(self, session_id: str) -> str:
        self._check_id(session_id)
        return os.path.join(self._sessions, session_id + ".json")

    def _acquire(self) -> None:
        self._lock.acquire()

    def _release(self) -> None:
        self._lock.release()

    def _save_locked(self, session: dict[str, Any]) -> None:
        tmp = os.path.join(self._sessions, session["id"] + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2)
        os.replace(tmp, self._path(session["id"]))

    def _load_locked(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # -- public contract -------------------------------------------------
    def start(self, query: str, task_id: str | None = None,
              project_id: str | None = None,
              strategy: str = "targeted_lookup", urls: list[str] | None = None) -> dict[str, Any]:
        if not query or not query.strip():
            raise ValueError("query required")
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy {strategy!r}")
        requested = list(urls or [])
        if len(requested) > MAX_SOURCES or any(not isinstance(u, str) or len(u) > 1024 for u in requested):
            raise ValueError("at most 10 URL strings of 1024 characters")
        for url in requested:
            _canonical_url(url)  # validate syntax; fetch tool enforces network boundary
        now = _utcnow()
        candidates, outline = _build_candidates(query.strip())
        if not config.get("research_candidates_enabled", True):
            candidates, outline = [], []

        session = {
            "id": uuid.uuid4().hex,
            "requested_urls": requested,
            "query": query.strip(),
            "query_history": [{"text": query.strip(), "at": now, "kind": "initial"}],
            "task_id": task_id,
            "project_id": project_id,
            "strategy": strategy,
            "strategy_reason": "caller-selected" if strategy else "default",
            "state": "selecting",
            "phase": "selecting",
            "next_action": "select_research_scope",
            "rev": 1,
            "created_at": now,
            "updated_at": now,
            "sources": [],
            "claims": [],
            "conflicts": [],
            "candidates": candidates,
            "outline": outline,
            "coverage": {},
            "repairs": 0,
            "repair_context": [],
            "report_attempts": [],
            "errors": [],
            "notes": [],
            "tools": [],
            "scripts": [],
            "file_changes": [],
            "report": None,
            "reports": [],

            "verified": False,
            "checkpoint": {"rev": 1, "updated_at": now},
        }
        self._acquire()
        try:
            self._save_locked(session)
        finally:
            self._release()
        return copy.deepcopy(session)

    @staticmethod
    def _next_action(phase: str) -> str:
        return {
            "selecting": "select_research_scope",
            "researching": "research",
            "synthesizing": "synthesize_sources",
            "writing": "write_report",
            "verifying": "verify_report",
            "publishing": "review_before_publish",
            "sleeping": "wait_for_next_cycle",
        }[phase]

    @staticmethod
    def _bounded_details(details: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(details, dict):
            raise ValueError("step details must be an object")
        try:
            encoded = json.dumps(details, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("step details must be JSON serializable") from exc
        if len(encoded) > MAX_LINEAGE_DETAIL_CHARS:
            raise ValueError(f"step details exceed {MAX_LINEAGE_DETAIL_CHARS} characters")
        return copy.deepcopy(details)

    def _lineage_path(self, value: Any) -> tuple[bool, str]:
        if not isinstance(value, str) or not value or len(value) > 1024:
            return False, "path must be a nonempty relative path"
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized) or ".." in parts:
            return False, "path escapes the research root"
        root = os.path.realpath(self.root)
        target = os.path.realpath(os.path.join(root, *parts))
        try:
            if os.path.commonpath((root, target)) != root:
                return False, "path escapes the research root"
        except ValueError:
            return False, "path escapes the research root"
        return True, "/".join(parts)

    def record_step(self, session_id: str, phase: str, kind: str,
                    details: dict[str, Any]) -> dict[str, Any]:
        """Persist bounded provenance only; scripts are recorded, never run."""
        if phase not in RESEARCH_PHASES:
            raise ValueError(f"unknown research phase {phase!r}")
        if kind not in {"query", "note", "tool", "script", "file_change", "checkpoint", "error"}:
            raise ValueError(f"unknown research step kind {kind!r}")
        entry = self._bounded_details(details)
        now = _utcnow()
        self._acquire()
        try:
            session = self._load_locked(session_id)
            if session is None:
                raise KeyError(f"unknown session {session_id!r}")
            if kind == "query":
                text = entry.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("query step requires nonempty text")
                session.setdefault("query_history", []).append({"text": text[:2000], "at": now, "kind": "follow_up"})
                session["query_history"] = session["query_history"][-MAX_LINEAGE_ITEMS:]
            elif kind == "note":
                session.setdefault("notes", []).append({**entry, "at": now})
                session["notes"] = session["notes"][-MAX_LINEAGE_ITEMS:]
            elif kind == "tool":
                session.setdefault("tools", []).append({**entry, "at": now})
                session["tools"] = session["tools"][-MAX_LINEAGE_ITEMS:]
            elif kind == "script":
                ok, safe_path = self._lineage_path(entry.get("path"))
                if not ok:
                    raise ValueError(safe_path)
                entry["path"] = safe_path
                session.setdefault("scripts", []).append({**entry, "at": now, "executed_by_store": False})
                session["scripts"] = session["scripts"][-MAX_LINEAGE_ITEMS:]
            elif kind == "file_change":
                ok, safe_path = self._lineage_path(entry.get("path"))
                change = {**entry, "at": now, "accepted": ok}
                if ok:
                    change["path"] = safe_path
                else:
                    change["error"] = safe_path
                session.setdefault("file_changes", []).append(change)
                session["file_changes"] = session["file_changes"][-MAX_LINEAGE_ITEMS:]
            elif kind == "error":
                session.setdefault("errors", []).append(entry)
                session["errors"] = session["errors"][-MAX_LINEAGE_ITEMS:]
            session["phase"] = phase
            session["next_action"] = self._next_action(phase)
            session["rev"] = int(session.get("rev", 0)) + 1
            session["updated_at"] = now
            session["checkpoint"] = {"rev": session["rev"], "phase": phase,
                                     "next_action": session["next_action"], "updated_at": now}
            self._save_locked(session)
            return copy.deepcopy(session)
        finally:
            self._release()

    def resume(self, session_id: str) -> dict[str, Any]:
        """Return persisted session evidence unchanged with a deterministic checkpoint."""
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id!r}")
        phase = session.get("phase")
        if phase not in RESEARCH_PHASES:
            phase = "verifying" if session.get("state") == "needs_review" else (
                "sleeping" if session.get("state") == "complete" else session.get("state", "selecting"))
        session["phase"] = phase
        session["next_action"] = self._next_action(phase)
        session.setdefault("checkpoint", {})
        session["checkpoint"].setdefault("rev", session.get("rev", 0))
        session["checkpoint"].setdefault("updated_at", session.get("updated_at", _utcnow()))
        session["checkpoint"].update({"phase": phase, "next_action": session["next_action"]})
        return session

    def request_repair(self, session_id: str, *, max_attempts: int = 1) -> dict[str, Any]:
        """Admit one explicit owner retry atomically without replacing evidence."""
        self._acquire()
        try:
            session = self._load_locked(session_id)
            if session is None:
                raise KeyError(f"unknown session {session_id!r}")
            if session["state"] == "researching" and session.get("repair_pending"):
                return copy.deepcopy(session)  # retry a partially committed admission
            if session["state"] != "needs_review":
                raise ValueError("only needs_review research can resume")
            used = int(session.get("owner_repair_attempts", 0))
            if used >= max_attempts or int(session.get("repairs", 0)) >= MAX_REPAIRS:
                raise ValueError("research repair budget exhausted")
            session["owner_repair_attempts"] = used + 1
            session["repair_pending"] = True
            session["state"] = "researching"
            session["phase"] = "verifying"
            session["next_action"] = "repair_report"
            session["rev"] += 1
            session["updated_at"] = _utcnow()
            session["checkpoint"] = {"rev": session["rev"], "phase": session["phase"],
                                     "next_action": session["next_action"], "updated_at": session["updated_at"]}
            self._save_locked(session)
            return copy.deepcopy(session)
        finally:
            self._release()

    def confirm_repair(self, session_id: str) -> dict[str, Any]:
        """Clear the recovery marker only after the original task is requeued."""
        self._acquire()
        try:
            session = self._load_locked(session_id)
            if session is None:
                raise KeyError(f"unknown session {session_id!r}")
            if session.get("repair_pending"):
                session["repair_pending"] = False
                session["rev"] += 1
                session["updated_at"] = _utcnow()
                session["checkpoint"] = {"rev": session["rev"], "phase": session["phase"],
                                         "next_action": session["next_action"], "updated_at": session["updated_at"]}
                self._save_locked(session)
            return copy.deepcopy(session)
        finally:
            self._release()

    def add_source(self, session_id: str, url: str, text: str) -> dict[str, Any]:

        if not text or not text.strip():
            raise ValueError("text required")
        self._acquire()
        try:
            session = self._load_locked(session_id)
            if session is None:
                raise KeyError(f"unknown session {session_id!r}")
            if session["state"] not in ("selecting", "researching", "needs_review"):
                raise ValueError(f"cannot add source in state {session['state']!r}")
            canon = _canonical_url(url)
            digest = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
            for kept in session["sources"]:
                if kept["content_hash"] == digest:
                    if url not in kept["aliases"]:
                        kept["aliases"].append(url)
                    session["updated_at"] = _utcnow()
                    self._save_locked(session)
                    dup = copy.deepcopy(kept)
                    dup["duplicate"] = True
                    return dup
            if len(session["sources"]) >= MAX_SOURCES:
                raise ValueError(f"source cap {MAX_SOURCES} reached")
            now = _utcnow()
            body = text.strip()[:MAX_SOURCE_CHARS]
            source = {
                "id": uuid.uuid4().hex[:12],
                "url": canon,
                "original_url": url,
                "aliases": [url],
                "excerpt": text[:300],
                                "text": text[:MAX_SOURCE_CHARS],
                "content_hash": digest,
                "retrieved_at": now,
                "text_len": len(text.strip()),
            }
            session["sources"].append(source)
            claims = extract_claims(body) or [body[:300]]
            for claim in claims[:5]:
                session["claims"].append({
                    "text": claim[:500],
                    "kind": _tag_claim(claim),
                    "source_id": source["id"],
                })
            session["conflicts"] = self._find_conflicts(session["claims"])
            session["state"] = "researching"
            session["phase"] = "researching"
            session["next_action"] = self._next_action("researching")
            session["rev"] += 1
            session["updated_at"] = now
            session["checkpoint"] = {"rev": session["rev"], "phase": session["phase"],
                                     "next_action": session["next_action"], "updated_at": now}
            self._save_locked(session)
            out = copy.deepcopy(source)
            out["duplicate"] = False
            return out
        finally:
            self._release()

    @staticmethod
    def _find_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        conflicts = []
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                a, b = claims[i], claims[j]
                if a["source_id"] == b["source_id"]:
                    continue
                ta, tb = _tokens(a["text"]), _tokens(b["text"])
                shared = sorted((ta & tb) - _STOPWORDS)
                if len(shared) < 3:
                    continue
                aneg = bool(ta & _NEG_CUES)
                bneg = bool(tb & _NEG_CUES)
                if aneg != bneg:
                    conflicts.append({
                        "kind": "candidate",
                        "source_ids": [a["source_id"], b["source_id"]],
                        "reason": "candidate conflict on: " + ", ".join(shared[:5]),
                    })
        return conflicts

    def finish(self, session_id: str, report: dict[str, Any]) -> dict[str, Any]:
        self._acquire()
        try:
            session = self._load_locked(session_id)
            if session is None:
                raise KeyError(f"unknown session {session_id!r}")
            if session["state"] not in ("researching", "selecting", "verifying",
                                        "complete", "needs_review"):
                raise ValueError(f"cannot finish in state {session['state']!r}")
            errors = self._report_errors(session, report)
            try:
                encoded_report = json.dumps(report, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                encoded_report = repr(report)
            if len(encoded_report) > MAX_REPORT_CHARS:
                report_snapshot: Any = {"truncated": True, "preview": encoded_report[:MAX_REPORT_CHARS]}
            else:
                report_snapshot = copy.deepcopy(report)
            attempt = {"at": _utcnow(), "report": report_snapshot, "errors": list(errors)}
            session.setdefault("report_attempts", []).append(attempt)
            session["report_attempts"] = session["report_attempts"][-MAX_LINEAGE_ITEMS:]
            if errors:
                session.setdefault("repair_context", []).append({
                    "at": attempt["at"], "errors": list(errors),
                    "previous_report": copy.deepcopy(session.get("report")),
                    "attempt": len(session["report_attempts"]),
                })
                session["repair_context"] = session["repair_context"][-MAX_REPAIR_CONTEXT:]

            if errors:
                if session["repairs"] >= MAX_REPAIRS:
                    session["errors"] = errors
                    session["rev"] += 1
                    session["updated_at"] = _utcnow()
                    session["checkpoint"] = {"rev": session["rev"], "phase": "verifying",
                                             "next_action": "verify_report", "updated_at": session["updated_at"]}
                    self._save_locked(session)
                    self._write_markdown(session)
                    raise ValueError(f"repair limit {MAX_REPAIRS} exceeded: {errors}")
                session["repairs"] += 1
                session["errors"] = errors
                session["state"] = "needs_review"
                session["phase"] = "verifying"
                session["next_action"] = self._next_action("verifying")
                session["verified"] = False
                session["rev"] += 1
                session["updated_at"] = _utcnow()
                session["checkpoint"] = {"rev": session["rev"], "phase": session["phase"],
                                         "next_action": session["next_action"],
                                         "updated_at": session["updated_at"]}
                self._save_locked(session)
                return copy.deepcopy(session)
            # structural proposal-transition check (raises, not a repair)
            proposals = self._checked_proposals(session, report.get("proposals", []))
            stored = {
                "findings": list(report.get("findings", [])),
                "citations": [dict(c) for c in report.get("citations", [])],
                "proposals": proposals,
            }
            session.setdefault("reports", []).append({"at": _utcnow(), "report": copy.deepcopy(stored)})
            session["reports"] = session["reports"][-MAX_LINEAGE_ITEMS:]
            session["report"] = stored
            session["errors"] = []
            session["coverage"] = self._coverage(session)
            for cand, cov in zip(session["candidates"],
                                 session["coverage"].get("hypotheses", [])):
                cand["lexical_coverage"] = cov["lexical_coverage"]
                cand["support"] = cov["lexical_coverage"]
            session["state"] = "verifying"
            session["phase"] = "verifying"
            session["next_action"] = self._next_action("verifying")
            if not session["sources"] or stored["findings"] and not stored["citations"]:
                session["state"] = "needs_review"
                session["phase"] = "verifying"
                session["next_action"] = self._next_action("verifying")
                session["verified"] = False
            else:
                session["state"] = "complete"
                session["phase"] = "sleeping"
                session["next_action"] = self._next_action("sleeping")
                session["verified"] = False  # citation integrity is not factual verification
                session["citation_integrity_checked"] = bool(stored["citations"])
            session["rev"] += 1
            session["updated_at"] = _utcnow()
            session["checkpoint"] = {"rev": session["rev"], "phase": session["phase"],
                                     "next_action": session["next_action"],
                                     "updated_at": session["updated_at"]}
            self._save_locked(session)
            self._write_markdown(session)
            return copy.deepcopy(session)
        finally:
            self._release()

    @staticmethod
    def _report_errors(session: dict[str, Any],
                       report: dict[str, Any]) -> list[str]:
        if not isinstance(report, dict):
            return ["report must be an object"]
        if not isinstance(report.get("findings"), list):
            return ["report.findings must be a list"]
        if not report["findings"] or not all(isinstance(f, str) and f.strip() for f in report["findings"]):
            return ["report.findings must contain nonempty strings"]
        if not isinstance(report.get("citations", []), list):
            return ["report.citations must be a list"]
        if len(json.dumps(report)) > MAX_REPORT_CHARS:
            return [f"report exceeds {MAX_REPORT_CHARS} chars"]
        kept = {s["id"] for s in session["sources"]}
        for cite in report.get("citations", []):
            if not isinstance(cite, dict) or cite.get("source_id") not in kept:
                return [f"citation references unknown source: {cite!r}"]
            quote = cite.get("quote")
            if quote:
                source = next(s for s in session["sources"] if s["id"] == cite["source_id"])
                if not isinstance(quote, str) or quote not in source.get("text", source.get("excerpt", "")):
                    return ["citation quote not found in retained source"]
        return []

    @staticmethod
    def _checked_proposals(session: dict[str, Any],
                           proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
        prev = {}
        if isinstance(session.get("report"), dict):
            for p in session["report"].get("proposals", []):
                prev[p["id"]] = p
        out = []
        now = _utcnow()
        for i, p in enumerate(proposals):
            if not isinstance(p, dict) or not p.get("title"):
                raise ValueError(f"bad proposal at index {i}")
            pid = p.get("id") or f"p{i + 1}"
            state = p.get("state", "proposed")
            if state not in PROPOSAL_STATES:
                raise ValueError(f"bad proposal state {state!r}")
            old = prev.get(pid)
            history = list(old.get("history", [])) if old else []
            if old is None:
                if state != "proposed":
                    raise ValueError(
                        f"new proposal {pid!r} must start as proposed")
            elif state != old["state"]:
                if state not in PROPOSAL_TRANSITIONS[old["state"]]:
                    raise ValueError(
                        f"illegal proposal transition "
                        f"{old['state']!r} -> {state!r}")
                history.append({"from": old["state"], "to": state, "at": now})
            entry = {
                "id": pid,
                "title": p["title"],
                "state": state,
                "provenance": p.get("provenance")
                or (old or {}).get("provenance")
                or f"session:{session['id']}@{session['rev']}",
                "history": history,
            }
            out.append(entry)
        return out

    @staticmethod
    def _coverage(session: dict[str, Any]) -> dict[str, Any]:
        pool: set[str] = set()
        for c in session["claims"]:
            pool |= _tokens(c["text"])
        hyps = []
        for cand in session["candidates"]:
            ht = _tokens(cand["text"]) - _STOPWORDS
            overlap = len(ht & pool)
            denom = max(len(ht), 1)
            coverage = round(min(1.0, overlap / denom), 3)
            hyps.append({"text": cand["text"], "lexical_coverage": coverage,
                         "support": coverage})

        covered = 0
        for item in session["outline"]:
            it = _tokens(item) - _STOPWORDS
            if len(it & pool) >= 2:
                covered += 1
        return {"hypotheses": hyps,
                "outline_covered": f"{covered}/{len(session['outline'])}"}

    def get(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)  # validates id -> path bound
        if not os.path.exists(path):
            if not _ID_RE.match(session_id or ""):
                raise ValueError(f"bad session id {session_id!r}")
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def list(self) -> list[dict[str, Any]]:
        out = []
        if not os.path.isdir(self._sessions):
            return out
        for name in sorted(os.listdir(self._sessions)):
            if name.endswith(".json"):
                with open(os.path.join(self._sessions, name),
                          encoding="utf-8") as f:
                    out.append(json.load(f))
        return out

    def export_markdown(self, session_id: str) -> str:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"unknown session {session_id!r}")
        return self._render_markdown(session)

    @staticmethod
    def _render_markdown(session: dict[str, Any]) -> str:
        lines = [f"# Research: {session['query']}", "",
                 f"- strategy: {session['strategy']} "
                 f"({session.get('strategy_reason', '')})",
                 f"- state: {session['state']} | verified: {session['verified']}",
                 f"- checkpoint: rev {session['checkpoint']['rev']} "
                 f"@ {session['checkpoint']['updated_at']}", ""]
        if session["candidates"]:
            lines.append("## Candidate hypotheses (unverified)")
            for c in session["candidates"]:
                lines.append(f"- {c['text']} (support {c.get('support', 0.0)})")
            lines.append("")
        lines.append("## Sources")
        for s in session["sources"]:
            lines.append(f"- [{s['id']}] {s['url']} "
                         f"(hash {s['content_hash'][:12]}, {s['retrieved_at']})")
            lines.append(f"  {s['excerpt']}")
        lines.append("")
        for c in session.get("conflicts", []):
            lines.append(f"> candidate conflict {c['source_ids']}: {c['reason']}")
        if session["conflicts"]:
            lines.append("")
        rep = session.get("report") or {}
        lines.append("## Findings")
        for f in rep.get("findings", []):
            lines.append(f"- {f}")
        lines.append("")
        lines.append("## Citations")
        for c in rep.get("citations", []):
            lines.append(f"- {c.get('source_id')}: {c.get('note', '')}")
        if rep.get("proposals"):
            lines.append("")
            lines.append("## Proposals (adoption states, separate from findings)")
            for p in rep["proposals"]:
                lines.append(f"- [{p['state']}] {p['title']} "
                             f"({p['id']}; provenance {p['provenance']})")
        for title, key in (("Query history", "query_history"), ("Notes", "notes"),
                           ("Executed tool metadata", "tools"), ("Scripts recorded (not executed by ResearchStore)", "scripts"),
                           ("File changes", "file_changes"), ("Errors", "errors"),
                           ("Report attempts", "report_attempts"), ("Prior reports", "reports")):
            entries = session.get(key, [])
            if not entries:
                continue
            lines.extend(("", f"## {title}"))
            for entry in entries:
                lines.append("- " + json.dumps(entry, ensure_ascii=False, default=str))
        return "\n".join(lines) + "\n"

    def _write_markdown(self, session: dict[str, Any]) -> str:
        path = os.path.join(self._reports, session["id"] + ".md")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(self._render_markdown(session))
        os.replace(tmp, path)
        return path
