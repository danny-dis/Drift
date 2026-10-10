"""Tests for drift/research.py — research + challenge engine."""
import pytest

from drift.research import (
    Challenge,
    Evidence,
    ResearchReport,
    RESEARCH_MODES,
    SourceComparison,
    VerificationResult,
    challenge_assumption,
    compare_sources,
    extract_claims,
    extract_evidence,
    generate_alternatives,
    get_mode,
    synthesize_findings,
    verify_claim,
)


class TestResearchModes:
    def test_get_mode(self):
        mode = get_mode("deep_dive")
        assert mode["max_searches"] == 8
        assert mode["synthesis_required"] is True

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            get_mode("nonexistent")

    def test_all_modes_have_required_fields(self):
        for name, meta in RESEARCH_MODES.items():
            assert "description" in meta
            assert "max_searches" in meta
            assert "max_sources" in meta
            assert "synthesis_required" in meta


class TestEvidenceExtraction:
    def test_extract_claims_with_indicator(self):
        text = "Studies show that regular exercise improves mental health."
        claims = extract_claims(text)
        assert len(claims) >= 1

    def test_extract_claims_with_percentage(self):
        text = "Research indicates that 75% of users prefer dark mode."
        claims = extract_claims(text)
        assert len(claims) >= 1

    def test_extract_claims_empty(self):
        claims = extract_claims("")
        assert claims == []

    def test_extract_claims_no_claims(self):
        text = "The weather is nice today. I went for a walk."
        claims = extract_claims(text)
        assert claims == []

    def test_extract_evidence(self):
        text = "Studies show that regular exercise improves mental health."
        evidence = extract_evidence(text, source="test_source")
        assert len(evidence) >= 1
        assert evidence[0].source == "test_source"
        assert evidence[0].confidence > 0

    def test_extract_evidence_marks_opinion(self):
        text = "I think that regular exercise is good for you."
        evidence = extract_evidence(text)
        # Should be marked as opinion with lower confidence
        if evidence:
            assert evidence[0].kind == "opinion"
            assert evidence[0].confidence < 0.5


class TestSourceComparison:
    def test_identical_sources(self):
        a = Evidence(text="Studies show exercise improves health", source="A")
        b = Evidence(text="Studies show exercise improves health", source="B")
        result = compare_sources(a, b)
        assert result.agreement >= 0.8

    def test_different_sources(self):
        a = Evidence(text="Studies show exercise improves health", source="A")
        b = Evidence(text="The stock market rose today", source="B")
        result = compare_sources(a, b)
        assert result.agreement < 0.3

    def test_partial_overlap(self):
        a = Evidence(text="Studies show exercise improves mental health", source="A")
        b = Evidence(text="Research indicates exercise benefits mental health", source="B")
        result = compare_sources(a, b)
        assert 0.2 <= result.agreement <= 0.8


class TestVerification:
    def test_supported_claim(self):
        claim = "exercise improves health"
        evidence = [
            Evidence(text="Studies show exercise improves health", confidence=0.8),
            Evidence(text="Research confirms exercise benefits", confidence=0.7),
        ]
        result = verify_claim(claim, evidence)
        assert result.verdict == "supported"
        assert result.confidence > 0.5

    def test_contradicted_claim(self):
        claim = "the stock market will rise tomorrow"
        evidence = [
            Evidence(text="Studies show exercise improves health significantly", confidence=0.8),
        ]
        result = verify_claim(claim, evidence)
        assert result.verdict == "contradicted"

    def test_insufficient_evidence(self):
        claim = "exercise cures cancer"
        evidence = []
        result = verify_claim(claim, evidence)
        assert result.verdict == "insufficient_evidence"
        assert result.confidence == 0.0

    def test_mixed_evidence(self):
        claim = "exercise improves health"
        evidence = [
            Evidence(text="Studies show exercise improves health", confidence=0.8),
            Evidence(text="The stock market rose today", confidence=0.1),
        ]
        result = verify_claim(claim, evidence)
        assert result.verdict == "insufficient_evidence"


class TestAlternatives:
    def test_generate_alternatives(self):
        claim = "exercise improves health"
        evidence = [
            Evidence(text="Diet also plays a major role in health outcomes"),
            Evidence(text="Sleep quality affects overall wellbeing"),
            Evidence(text="Studies show exercise improves health"),
        ]
        alternatives = generate_alternatives(claim, evidence, max_alternatives=2)
        assert len(alternatives) >= 1

    def test_no_alternatives_when_empty(self):
        alternatives = generate_alternatives("test", [])
        assert alternatives == []


class TestChallengeEngine:
    def test_challenge_absolute_claim(self):
        text = "All users always prefer dark mode."
        challenges = challenge_assumption(text)
        assert len(challenges) >= 1
        assert any(c.kind == "absolute_claim" for c in challenges)

    def test_challenge_certainty(self):
        text = "Clearly this is the best approach."
        challenges = challenge_assumption(text)
        assert len(challenges) >= 1
        assert any(c.kind == "unwarranted_certainty" for c in challenges)

    def test_challenge_necessity(self):
        text = "You must use this framework."
        challenges = challenge_assumption(text)
        assert len(challenges) >= 1
        assert any(c.kind == "necessity_assumption" for c in challenges)

    def test_challenge_value_judgment(self):
        text = "This is the best solution available."
        challenges = challenge_assumption(text)
        assert len(challenges) >= 1
        assert any(c.kind == "value_judgment" for c in challenges)

    def test_challenge_causal(self):
        text = "Sales increased because of the new design."
        challenges = challenge_assumption(text)
        assert len(challenges) >= 1
        assert any(c.kind == "causal_assumption" for c in challenges)

    def test_no_challenge_for_neutral(self):
        text = "The meeting is scheduled for 3 PM."
        challenges = challenge_assumption(text)
        assert challenges == []


class TestSynthesizeFindings:
    def test_synthesize_basic(self):
        evidence = [
            Evidence(text="Studies show exercise improves health", confidence=0.8, kind="fact"),
            Evidence(text="Research confirms benefits", confidence=0.7, kind="observation"),
        ]
        report = synthesize_findings(
            topic="exercise and health",
            mode="deep_dive",
            evidence_list=evidence,
            challenges=[],
            alternatives=[],
        )
        assert report.topic == "exercise and health"
        assert report.mode == "deep_dive"
        assert len(report.findings) >= 1
        assert report.confidence > 0.5

    def test_synthesize_with_challenges(self):
        evidence = [
            Evidence(text="Studies show exercise improves health", confidence=0.8),
        ]
        challenges = [
            Challenge(target="test", challenge="challenge text", confidence=0.6),
        ]
        report = synthesize_findings(
            topic="exercise",
            mode="deep_dive",
            evidence_list=evidence,
            challenges=challenges,
            alternatives=[],
        )
        assert len(report.challenges) == 1
        # Confidence should be reduced by challenges
        assert report.confidence < 0.8

    def test_synthesize_with_alternatives(self):
        evidence = [
            Evidence(text="Studies show exercise improves health", confidence=0.8),
        ]
        alternatives = ["Diet also matters", "Sleep is important"]
        report = synthesize_findings(
            topic="exercise",
            mode="deep_dive",
            evidence_list=evidence,
            challenges=[],
            alternatives=alternatives,
        )
        assert len(report.alternatives) == 2

    def test_synthesize_empty(self):
        report = synthesize_findings(
            topic="empty",
            mode="targeted_lookup",
            evidence_list=[],
            challenges=[],
            alternatives=[],
        )
        assert report.confidence < 0.5
        assert report.findings == []
