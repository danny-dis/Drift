"""Drift's project/idea intelligence layer.

Durable state lives outside the model. This module turns it into bounded,
replayable evidence packets so a small/local model can work indefinitely
without carrying a perpetual transcript.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from drift.context import MemoryBlock, build_packet, decay_recency, keyword_relevance


@dataclass
class Idea:
    id: str
    text: str
    status: str = "captured"
    concepts: list[str] = field(default_factory=list)
    related_projects: list[str] = field(default_factory=list)
    confidence: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class Project:
    id: str
    name: str
    repo: str
    local_path: str | None = None
    importance: float = 0.5
    last_seen_commit: str | None = None
    last_round: str | None = None


@dataclass
class DriftEvent:
    kind: str
    source: str
    summary: str
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    related_projects: list[str] = field(default_factory=list)
    related_ideas: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DriftLedger:
    """Durable structured ledger for ideas, projects and observations."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "drift_ledger.json"
        self.data: dict[str, Any] = {
            "schema": 2,
            "ideas": [],
            "projects": [],
            "events": [],
            "mind_map": {"nodes": [], "edges": []},
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
                self.data.update(loaded)
                self.data["schema"] = max(2, int(self.data.get("schema", 1)))
            except (OSError, ValueError, TypeError):
                pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    def add_idea(self, text: str, concepts: list[str] | None = None) -> Idea:
        index = len(self.data["ideas"])
        idea = Idea(id=f"idea-{index:06d}", text=text.strip(), concepts=concepts or [])
        self.data["ideas"].append(asdict(idea))
        self._node(idea.id, "idea", idea.text)
        for concept in idea.concepts:
            cid = "concept:" + _slug(concept)
            self._node(cid, "concept", concept)
            self._edge(idea.id, cid, "contains")
        self.save()
        return idea

    def add_project(self, project: Project) -> None:
        existing = next((p for p in self.data["projects"] if p["id"] == project.id), None)
        if existing:
            existing.update(asdict(project))
        else:
            self.data["projects"].append(asdict(project))
        self._node(project.id, "project", project.name)
        self.save()

    def add_event(self, event: DriftEvent) -> None:
        self.data["events"].append(asdict(event))
        self.data["events"] = self.data["events"][-5000:]
        self.save()

    def packet_for_project(self, project_id: str, task: str, objective: str, query: str = "") -> str:
        """Build a ranked, provenance-preserving working set for one project.

        The model sees selected memory, not the entire ledger. The lexical
        relevance score is intentionally cheap; dmr-X can later replace it with
        embeddings/reranking without changing this interface.
        """
        project = next((p for p in self.data["projects"] if p["id"] == project_id), None)
        project_name = project["name"] if project else project_id
        related_events = [e for e in self.data["events"] if project_id in e.get("related_projects", [])]
        related_ideas = [i for i in self.data["ideas"] if project_id in i.get("related_projects", [])]
        memories: list[MemoryBlock] = []

        for e in related_events:
            text = e.get("summary", "")
            relevance = keyword_relevance(query or project_name, text)
            memories.append(MemoryBlock(
                id=f"event:{e.get('timestamp','')}:{text[:20]}", text=text,
                kind=e.get("kind", "observation"), importance=0.7,
                confidence=float(e.get("confidence", 0.5)), relevance=max(relevance, 0.35),
                recency=decay_recency(e.get("timestamp", "")),
                provenance=tuple(e.get("evidence", [])), created_at=e.get("timestamp", ""),
            ))
        for i in related_ideas:
            text = i.get("text", "")
            relevance = keyword_relevance(query or project_name, text)
            memories.append(MemoryBlock(
                id=i.get("id", "idea"), text=text, kind="idea",
                importance=0.65, confidence=float(i.get("confidence", 0.5)),
                relevance=max(relevance, 0.30), recency=decay_recency(i.get("created_at", "")),
                created_at=i.get("created_at", ""),
            ))

        state = [f"name={project_name}"]
        if project:
            state.append(f"repo={project.get('repo', '')}")
            if project.get("last_seen_commit"):
                state.append(f"last_seen_commit={project['last_seen_commit']}")

        # drift.md is a compact durable summary and therefore gets priority over
        # replaying old transcripts. It is included as evidence, not as truth.
        if project and project.get("local_path"):
            intelligence = read_drift_md(project["local_path"])
            if intelligence:
                memories.append(MemoryBlock(
                    id=f"drift-md:{project_id}", text=intelligence, kind="project_state",
                    importance=0.9, confidence=0.8, relevance=0.9, recency=0.8,
                    provenance=(str(Path(project["local_path"]) / "drift.md"),),
                ))

        return build_packet(
            task=task,
            objective=objective,
            project_state=state,
            constraints=[
                "Separate fact, observation, hypothesis and recommendation.",
                "Cite evidence for consequential claims.",
                "Do not treat missing context as proof that something does not exist.",
            ],
            memories=memories,
        ).render()

    def _node(self, node_id: str, kind: str, label: str) -> None:
        if not any(n["id"] == node_id for n in self.data["mind_map"]["nodes"]):
            self.data["mind_map"]["nodes"].append({"id": node_id, "kind": kind, "label": label})

    def _edge(self, source: str, target: str, relation: str) -> None:
        edge = {"source": source, "target": target, "relation": relation}
        if edge not in self.data["mind_map"]["edges"]:
            self.data["mind_map"]["edges"].append(edge)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80]


def git_snapshot(path: str) -> dict[str, Any]:
    """Read cheap deterministic Git facts. No model is needed for this step."""
    root = Path(path)

    def run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    status = run("status", "--porcelain")
    commit = run("rev-parse", "HEAD")
    branch = run("branch", "--show-current")
    return {
        "commit": commit,
        "branch": branch,
        "dirty": bool(status),
        "changed_files": [line[3:] for line in status.splitlines() if len(line) >= 4],
    }


def git_diff_summary(path: str, old_commit: str | None = None) -> dict[str, Any]:
    """Get bounded, deterministic change metadata before invoking a model."""
    root = Path(path)
    base = old_commit or "HEAD~1"

    def run(*args: str) -> str:
        try:
            return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    stat = run("diff", "--stat", base, "HEAD")
    names = run("diff", "--name-status", base, "HEAD")
    return {
        "base": base,
        "stat": stat[:4000],
        "files": names.splitlines()[:100],
        "file_count": len(names.splitlines()),
    }


def read_drift_md(path: str, limit: int = 6000) -> str:
    target = Path(path) / "drift.md"
    try:
        return target.read_text(errors="replace")[:limit]
    except (OSError, UnicodeError):
        return ""


def update_drift_md(
    path: str, *, state: str, findings: list[str], challenges: list[str],
    alternatives: list[str], questions: list[str] | None = None,
    evidence: list[str] | None = None,
) -> None:
    """Maintain a compact current-state document, not an append-only diary.

    Older updates are summarized away by replacing the managed sections. Raw
    evidence remains in the ledger, so compaction never destroys provenance.
    """
    target = Path(path) / "drift.md"
    existing = target.read_text(errors="replace") if target.exists() else ""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    questions = questions or []
    evidence = evidence or []

    def bullets(values: list[str], fallback: str = "None recorded.") -> str:
        return "\n".join(f"- {x}" for x in values) if values else f"- {fallback}"

    managed = (
        "# Drift Intelligence\n\n"
        "<!-- DRIFT-MANAGED: current project intelligence. Raw history lives in the Drift ledger. -->\n\n"
        f"_Last synthesized: {stamp}_\n\n"
        "## Current State\n" + (state.strip() or "Unknown — investigate before making assumptions.") + "\n\n"
        "## New Findings\n" + bullets(findings) + "\n\n"
        "## Challenges / Risks\n" + bullets(challenges) + "\n\n"
        "## Alternatives\n" + bullets(alternatives) + "\n\n"
        "## Open Questions\n" + bullets(questions) + "\n\n"
        "## Evidence / Provenance\n" + bullets(evidence) + "\n"
    )

    # Preserve human-authored material outside the managed marker when present.
    human = existing.split("<!-- DRIFT-MANAGED", 1)[0].strip() if existing else ""
    if human.startswith("# Drift Intelligence"):
        human = human[len("# Drift Intelligence"):].strip()
    prefix = "# Drift Intelligence\n\n"
    if human:
        prefix += human + "\n\n"
    target.write_text(prefix + managed.split("# Drift Intelligence\n\n", 1)[1])
