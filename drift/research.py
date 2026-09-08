"""Research + challenge engine for Drift (Phase 5).

Handles research workflows: extracting evidence from text, comparing
sources, verifying claims, generating alternatives, and challenging
assumptions. All logic is deterministic and cheap — no model calls
except where explicitly noted.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

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
