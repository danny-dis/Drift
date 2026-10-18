"""Drift's project/idea intelligence layer.

Durable state lives outside the model. This module turns it into bounded,
replayable evidence packets so a small/local model can work indefinitely
without carrying a perpetual transcript.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from drift.context import MemoryBlock, build_packet, decay_recency, keyword_relevance
from drift.git_read import read_git
from drift.project_document import read_document, write_document

logger = logging.getLogger("drift.organism")


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
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {
            "schema": 2,
            "ideas": [],
            "projects": [],
            "events": [],
            "mind_map": {"nodes": [], "edges": []},
        }
        self._load()

    def _load(self) -> None:
        self._refresh_locked()

    def reload(self) -> None:
        """Re-read persisted state so a stale in-memory copy can't clobber others."""
        with self._lock:
            self._refresh_locked()

    def _refresh_locked(self) -> None:
        """Re-read file into memory. Caller must hold the lock."""
        self.data = self._read_checkpoint()

    def _read_checkpoint(self) -> dict[str, Any]:
        fresh = {
            "schema": 2, "ideas": [], "projects": [],
            "events": [], "mind_map": {"nodes": [], "edges": []},
        }
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return fresh
        except (OSError, ValueError):
            logger.error("Ledger checkpoint unreadable; refusing to replace existing work")
            raise
        if not isinstance(loaded, dict) or type(loaded.get("schema")) is not int:
            raise ValueError("Invalid ledger checkpoint; repair required")
        if loaded["schema"] not in (1, 2):
            raise ValueError("Unsupported ledger schema; repair required")
        for key in ("ideas", "projects", "events"):
            if not isinstance(loaded.get(key), list) or any(not isinstance(item, dict) for item in loaded[key]):
                raise ValueError(f"Invalid ledger {key}; repair required")
        graph = loaded.get("mind_map")
        if not isinstance(graph, dict) or any(not isinstance(graph.get(key), list) for key in ("nodes", "edges")):
            raise ValueError("Invalid ledger mind map; repair required")
        for key, fields in (("nodes", ("id",)), ("edges", ("source", "target", "relation"))):
            if any(not isinstance(item, dict) or any(not isinstance(item.get(field), str) for field in fields)
                   for item in graph[key]):
                raise ValueError(f"Invalid ledger {key} record; repair required")
        fresh.update(loaded)
        fresh["schema"] = 2
        return fresh

    def _persist_locked(self) -> None:
        """Atomic tmp+replace write. Caller must hold the lock."""
        payload = json.dumps(self.data, indent=2, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".ledger-", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _next_idea_id(self) -> str:
        best = -1
        for item in self.data.get("ideas", []):
            raw = str(item.get("id", ""))
            if raw.startswith("idea-"):
                try:
                    best = max(best, int(raw.split("-")[1]))
                except (ValueError, IndexError):
                    continue
        return f"idea-{best + 1:06d}"

    def mutate(self, change):
        """Apply one domain mutation against refreshed state atomically."""
        with self._lock:
            self._refresh_locked()
            result = change(self.data)
            self._persist_locked()
            return result

    def save(self) -> None:
        with self._lock:
            self._read_checkpoint()
            self._persist_locked()

    def add_idea(self, text: str, concepts: list[str] | None = None) -> Idea:
        # Single critical section: refresh + mutate + persist so concurrent
        # writers can't interleave a stale read between reload and save.
        with self._lock:
            self._refresh_locked()
            idea = Idea(id=self._next_idea_id(), text=text.strip(), concepts=concepts or [])
            self.data["ideas"].append(asdict(idea))
            self._node_locked(idea.id, "idea", idea.text)
            for concept in idea.concepts:
                cid = "concept:" + _slug(concept)
                self._node_locked(cid, "concept", concept)
                self._edge_locked(idea.id, cid, "contains")
            self._persist_locked()
            return idea

    def add_project(self, project: Project) -> None:
        with self._lock:
            self._refresh_locked()
            existing = next((p for p in self.data["projects"] if p["id"] == project.id), None)
            if existing:
                existing.update(asdict(project))
            else:
                self.data["projects"].append(asdict(project))
            self._node_locked(project.id, "project", project.name)
            self._persist_locked()

    def add_event(self, event: DriftEvent) -> None:
        with self._lock:
            self._refresh_locked()
            self.data["events"].append(asdict(event))
            self.data["events"] = self.data["events"][-5000:]
            self._persist_locked()

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
        with self._lock:
            self._node_locked(node_id, kind, label)

    def _node_locked(self, node_id: str, kind: str, label: str) -> None:
        if not any(n["id"] == node_id for n in self.data["mind_map"]["nodes"]):
            self.data["mind_map"]["nodes"].append({"id": node_id, "kind": kind, "label": label})

    def _edge(self, source: str, target: str, relation: str) -> None:
        with self._lock:
            self._edge_locked(source, target, relation)

    def _edge_locked(self, source: str, target: str, relation: str) -> None:
        edge = {"source": source, "target": target, "relation": relation}
        if edge not in self.data["mind_map"]["edges"]:
            self.data["mind_map"]["edges"].append(edge)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:80]


def git_snapshot(path: str) -> dict[str, Any]:
    """Read cheap deterministic Git facts. No model is needed for this step."""
    status = read_git(path, "status", "--porcelain")
    commit = read_git(path, "rev-parse", "HEAD")
    branch = read_git(path, "branch", "--show-current")
    return {
        "commit": commit,
        "branch": branch,
        "dirty": bool(status),
        "changed_files": [line[3:] for line in status.splitlines() if len(line) >= 4],
    }


def git_diff_summary(path: str, old_commit: str | None = None) -> dict[str, Any]:
    """Get bounded, deterministic change metadata before invoking a model."""
    base = old_commit or "HEAD~1"
    stat = read_git(path, "diff", "--stat", base, "HEAD")
    names = read_git(path, "diff", "--name-status", base, "HEAD")
    return {
        "base": base,
        "stat": stat[:4000],
        "files": names.splitlines()[:100],
        "file_count": len(names.splitlines()),
    }


def read_drift_md(path: str, limit: int = 6000) -> str:
    try:
        return read_document(path, limit)
    except (OSError, ValueError):
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
    existing = read_document(path)
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
    write_document(path, prefix + managed.split("# Drift Intelligence\n\n", 1)[1])
