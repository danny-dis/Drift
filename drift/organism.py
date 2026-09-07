"""Drift's project/idea intelligence layer.

This layer deliberately stores structured state instead of relying on a long
LLM conversation.  It is safe to run continuously with a small model because
work is decomposed into bounded, replayable events.
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

from drift.context import build_packet


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
            "schema": 1,
            "ideas": [],
            "projects": [],
            "events": [],
            "mind_map": {"nodes": [], "edges": []},
        }
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text()))
            except (OSError, ValueError):
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
        # Bound the event ledger. Durable summaries live in project intelligence docs.
        self.data["events"] = self.data["events"][-5000:]
        self.save()

    def packet_for_project(self, project_id: str, task: str, objective: str) -> str:
        project = next((p for p in self.data["projects"] if p["id"] == project_id), None)
        related_events = [e["summary"] for e in self.data["events"] if project_id in e.get("related_projects", [])]
        related_ideas = [i["text"] for i in self.data["ideas"] if project_id in i.get("related_projects", [])]
        state = []
        if project:
            state.append(f"name={project['name']}")
            state.append(f"repo={project['repo']}")
            if project.get("last_seen_commit"):
                state.append(f"last_seen_commit={project['last_seen_commit']}")
        return build_packet(
            task=task,
            objective=objective,
            recent_events=related_events,
            relevant_ideas=related_ideas,
            project_state=state,
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


def update_drift_md(path: str, *, state: str, findings: list[str], challenges: list[str], alternatives: list[str]) -> None:
    """Maintain a compact project intelligence document instead of a diary."""
    target = Path(path) / "drift.md"
    if target.exists():
        existing = target.read_text()
    else:
        existing = "# Drift Intelligence\n\n"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = {
        "Current State": state.strip() or "Unknown — investigate before making assumptions.",
        "New Findings": "\n".join(f"- {x}" for x in findings) or "- None recorded.",
        "Challenges / Risks": "\n".join(f"- {x}" for x in challenges) or "- None recorded.",
        "Alternatives": "\n".join(f"- {x}" for x in alternatives) or "- None recorded.",
    }
    block = [f"## Drift update — {stamp}"]
    for title, body in sections.items():
        block.extend([f"### {title}", body, ""])
    marker = "## Drift update —"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n\n"
    target.write_text(existing + "\n".join(block) + "\n")
