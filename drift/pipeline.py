"""Idea-to-project qualification pipeline for Drift.

Turns unstructured owner thoughts into structured ideas, matches them to
existing projects with scored explanations, qualifies them as PROJECT /
RESEARCH / PARKED, and maintains compact project intelligence (drift.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from drift.organism import DriftEvent, DriftLedger, Idea, Project, update_drift_md
from drift.task import TaskStore


@dataclass
class ProjectMatch:
    """A scored match between an idea and an existing project."""
    project_id: str
    project_name: str
    score: float  # 0.0-1.0
    explanation: str  # human-readable rationale
    match_reasons: list[str] = field(default_factory=list)


class IdeaPipeline:
    """Qualify ideas and connect them to projects."""

    VALID_QUALIFICATIONS = ("PROJECT", "RESEARCH", "PARKED")

    def __init__(self, ledger: DriftLedger, tasks: TaskStore, config: dict):
        self.ledger = ledger
        self.tasks = tasks
        self.config = config

    # ------------------------------------------------------------------
    # Idea capture
    # ------------------------------------------------------------------
    def capture_idea(self, text: str, concepts: list[str] | None = None) -> Idea:
        """Create a structured idea from unstructured text.

        If ``concepts`` is not provided, they are extracted automatically
        via :meth:`extract_concepts`.
        """
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("idea text must not be empty")

        extracted = concepts if concepts is not None else self.extract_concepts(cleaned)
        idea = self.ledger.add_idea(cleaned, extracted)

        self.ledger.add_event(DriftEvent(
            kind="observation",
            source="pipeline",
            summary=f"Captured idea {idea.id}: {cleaned[:120]}",
            confidence=0.7,
            related_ideas=[idea.id],
        ))
        return idea

    # ------------------------------------------------------------------
    # Concept extraction
    # ------------------------------------------------------------------
    def extract_concepts(self, text: str) -> list[str]:
        """Extract key concepts from text.

        Simple heuristic: noun-phrase-like tokens of >= 3 chars, lower-cased,
        de-duplicated, preserving first-seen order. No external deps.
        """
        # Split on non-alphanumeric (plus hyphen/underscore) and filter.
        tokens = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_\-]+", text)
        seen: set[str] = set()
        concepts: list[str] = []
        for tok in tokens:
            key = tok.lower().strip("-_")
            if len(key) >= 3 and key not in seen:
                seen.add(key)
                concepts.append(key)
        return concepts

    # ------------------------------------------------------------------
    # Project matching
    # ------------------------------------------------------------------
    def match_project(self, idea_id: str) -> list[ProjectMatch]:
        """Find matching projects for an idea, scored and sorted high→low."""
        idea = next((i for i in self.ledger.data["ideas"] if i["id"] == idea_id), None)
        if not idea:
            raise KeyError(f"idea {idea_id} not found")

        idea_text = idea.get("text", "")
        idea_concepts = set(idea.get("concepts", []))

        matches: list[ProjectMatch] = []
        for project in self.ledger.data["projects"]:
            match = self.score_match(idea, project)
            if not self._has_weak_match(match.score):
                matches.append(match)

        matches.sort(key=lambda m: m.score, reverse=True)

        # Persist related-project links on the idea (best matches only).
        top = [m.project_id for m in matches[:3]]
        if top:
            idea.setdefault("related_projects", [])
            for pid in top:
                if pid not in idea["related_projects"]:
                    idea["related_projects"].append(pid)
            self.ledger.save()

        return matches

    def score_match(self, idea: dict, project: dict) -> ProjectMatch:
        """Score how well an idea matches a project, with explanation."""
        idea_text = idea.get("text", "")
        idea_concepts = set(idea.get("concepts", []))

        project_name = project.get("name", project.get("id", ""))
        project_repo = project.get("repo", "")
        project_text = " ".join([project_name, project_repo]).strip()

        # Keyword overlap between idea text and project name+repo.
        overlap = self._keyword_overlap(idea_text, project_text)

        # Concept overlap between idea concepts and project concepts.
        project_concepts = set(self.extract_concepts(project_text))
        shared_concepts = idea_concepts & project_concepts
        concept_score = len(shared_concepts) / max(len(idea_concepts), 1)

        # Prior relationship bonus.
        prior_bonus = 0.1 if project["id"] in idea.get("related_projects", []) else 0.0

        # Weighted blend, clamped to [0, 1].
        raw_score = (0.45 * overlap) + (0.45 * concept_score) + prior_bonus
        score = max(0.0, min(1.0, round(raw_score, 3)))

        match = ProjectMatch(
            project_id=project["id"],
            project_name=project_name,
            score=score,
            explanation="",  # populated below
            match_reasons=[],
        )

        reasons: list[str] = []
        if shared_concepts:
            reasons.append(f"shared concepts: {', '.join(sorted(shared_concepts))}")
        if overlap >= 0.3:
            reasons.append(f"keyword overlap ({overlap:.0%})")
        if prior_bonus:
            reasons.append("previously linked")
        if not reasons:
            reasons.append("weak lexical similarity")

        match.match_reasons = reasons
        match.explanation = self._generate_explanation(match, idea_text)
        return match

    # ------------------------------------------------------------------
    # Qualification
    # ------------------------------------------------------------------
    def qualify_idea(self, idea_id: str, qualification: str) -> Idea:
        """Set an idea's qualification to PROJECT, RESEARCH, or PARKED."""
        qualification = qualification.upper()
        if qualification not in self.VALID_QUALIFICATIONS:
            raise ValueError(
                f"invalid qualification {qualification!r}; "
                f"expected one of {self.VALID_QUALIFICATIONS}"
            )

        idea = next((i for i in self.ledger.data["ideas"] if i["id"] == idea_id), None)
        if not idea:
            raise KeyError(f"idea {idea_id} not found")

        idea["status"] = qualification
        self.ledger.save()

        self.ledger.add_event(DriftEvent(
            kind="decision",
            source="pipeline",
            summary=f"Idea {idea_id} qualified as {qualification}",
            confidence=0.8,
            related_ideas=[idea_id],
        ))

        # Reconstruct Idea dataclass for the return type.
        return Idea(
            id=idea["id"],
            text=idea["text"],
            status=idea["status"],
            concepts=idea.get("concepts", []),
            related_projects=idea.get("related_projects", []),
            confidence=idea.get("confidence", 0.5),
            created_at=idea["created_at"],
        )

    # ------------------------------------------------------------------
    # Project intelligence
    # ------------------------------------------------------------------
    def update_project_intelligence(
        self,
        project_id: str,
        findings: list[str],
        challenges: list[str],
        alternatives: list[str],
        questions: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        """Update a project's drift.md via the existing update_drift_md()."""
        project = next(
            (p for p in self.ledger.data["projects"] if p["id"] == project_id), None
        )
        if not project:
            raise KeyError(f"project {project_id} not found")
        local_path = project.get("local_path")
        if not local_path:
            raise ValueError(f"project {project_id} has no local_path")

        state = f"{project.get('name', project_id)} — {project.get('repo', '')}".strip(" -")
        update_drift_md(
            local_path,
            state=state,
            findings=findings,
            challenges=challenges,
            alternatives=alternatives,
            questions=questions,
            evidence=evidence,
        )

        self.ledger.add_event(DriftEvent(
            kind="observation",
            source="pipeline",
            summary=f"Updated intelligence for {project_id}: "
                    f"{len(findings)} findings, {len(challenges)} challenges",
            confidence=0.75,
            related_projects=[project_id],
        ))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def get_idea_status(self, idea_id: str) -> dict:
        """Return idea with its matches and qualification."""
        idea = next((i for i in self.ledger.data["ideas"] if i["id"] == idea_id), None)
        if not idea:
            raise KeyError(f"idea {idea_id} not found")

        matches = self.match_project(idea_id)
        return {
            "idea": idea,
            "qualification": idea.get("status", "captured"),
            "matches": [
                {
                    "project_id": m.project_id,
                    "project_name": m.project_name,
                    "score": m.score,
                    "explanation": m.explanation,
                    "match_reasons": m.match_reasons,
                }
                for m in matches
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _keyword_overlap(text1: str, text2: str) -> float:
        """Jaccard-like overlap of >=3 char tokens between two strings."""
        def _tokens(t: str) -> set[str]:
            return {tok.lower() for tok in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9_\-]+", t)
                    if len(tok) >= 3}

        a, b = _tokens(text1), _tokens(text2)
        if not a or not b:
            return 0.0
        intersection = a & b
        union = a | b
        return len(intersection) / len(union)

    @staticmethod
    def _has_weak_match(score: float, threshold: float = 0.3) -> bool:
        """Return True if the match score is below the threshold (reject)."""
        return score < threshold

    @staticmethod
    def _generate_explanation(match: ProjectMatch, idea_text: str) -> str:
        """Produce a human-readable rationale for a project match."""
        if match.score >= 0.7:
            strength = "strong"
        elif match.score >= 0.4:
            strength = "moderate"
        else:
            strength = "weak"

        snippet = idea_text[:80] + ("…" if len(idea_text) > 80 else "")
        reasons = "; ".join(match.match_reasons) if match.match_reasons else "lexical similarity"
        return (
            f"{strength.capitalize()} match ({match.score:.0%}) between idea "
            f'"{snippet}" and project "{match.project_name}". '
            f"Reasons: {reasons}."
        )


# ----------------------------------------------------------------------
# Top-level helper
# ----------------------------------------------------------------------

def _keyword_overlap(text1: str, text2: str) -> float:
    """Jaccard-like overlap of >=3 char tokens between two strings. (Module-level wrapper)"""
    return IdeaPipeline._keyword_overlap(text1, text2)


def _has_weak_match(score: float, threshold: float = 0.3) -> bool:
    """Return True if the match score is below the threshold. (Module-level wrapper)"""
    return IdeaPipeline._has_weak_match(score, threshold)


def create_project_from_idea(
    pipeline: IdeaPipeline,
    idea_id: str,
    name: str,
    repo: str,
    local_path: str | None = None,
) -> Project:
    """Convert a qualified idea into a tracked project.

    Uses the pipeline's ledger so the project is registered and an event
    is emitted linking back to the originating idea.
    """
    idea = next(
        (i for i in pipeline.ledger.data["ideas"] if i["id"] == idea_id), None
    )
    if not idea:
        raise KeyError(f"idea {idea_id} not found")

    project_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80]
    project = Project(
        id=project_id,
        name=name,
        repo=repo,
        local_path=local_path,
    )
    pipeline.ledger.add_project(project)

    # Link idea → project bidirectionally.
    idea.setdefault("related_projects", [])
    if project_id not in idea["related_projects"]:
        idea["related_projects"].append(project_id)
    pipeline.ledger.save()

    pipeline.ledger.add_event(DriftEvent(
        kind="decision",
        source="pipeline",
        summary=f"Created project {project_id} from idea {idea_id}",
        confidence=0.85,
        related_projects=[project_id],
        related_ideas=[idea_id],
    ))
    return project