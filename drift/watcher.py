"""Continuous Git/project watcher for Drift's project intelligence layer.

Monitors registered projects for new commits, meaningful diffs, and branches.
Deterministic and cheap: 1000 git events → ~5 model analyses. Never invokes
the model for every Git event.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from drift.organism import DriftLedger, git_diff_summary, git_snapshot
from drift.task import TaskStore

logger = logging.getLogger("drift.watcher")

# Keywords that indicate a commit is significant
SIGNIFICANT_KEYWORDS = {
    "fix", "feat", "breaking", "BREAKING", "refactor", "security", "perf",
    "hotfix", "release", "merge", "revert", "deprecate", "remove", "delete",
    "critical", "bug", "crash", "data loss", "vulnerability", "CVE",
    "migration", "schema", "api change", "public api", "contract",
}


@dataclass
class GitChange:
    """A detected change in a watched project."""
    project_id: str
    commit_hash: str
    commit_message: str
    author: str
    timestamp: str
    changed_files: list[str]
    diff_stat: str
    significance: float = 0.0
    branch: str = ""


class GitWatcher:
    """Watch registered projects for meaningful changes."""

    def __init__(self, ledger: DriftLedger, tasks: TaskStore, config: dict):
        self.ledger = ledger
        self.tasks = tasks
        self.config = config
        self._watched: dict[str, str] = {}  # project_id -> local_path

    def register_project(self, project_id: str, local_path: str) -> None:
        """Add a project to the watch list."""
        self._watched[project_id] = local_path
        logger.info(f"Watching project {project_id} at {local_path}")

    def get_watched_projects(self) -> list[str]:
        """Return list of watched project IDs."""
        return list(self._watched.keys())

    def scan_all(self) -> list[GitChange]:
        """Scan all registered projects for changes since last seen commit."""
        changes: list[GitChange] = []
        for project_id, local_path in self._watched.items():
            try:
                changes.extend(self.scan_project(project_id, local_path))
            except Exception as e:
                logger.warning(f"Failed to scan {project_id}: {e}")
        return changes

    def scan_project(self, project_id: str, local_path: str | None = None) -> list[GitChange]:
        """Scan a single project for new commits since last seen."""
        if local_path is None:
            local_path = self._watched.get(project_id)
        if not local_path:
            return []

        project = next(
            (p for p in self.ledger.data.get("projects", []) if p["id"] == project_id),
            None,
        )
        if not project:
            return []

        last_seen = project.get("last_seen_commit")
        snapshot = git_snapshot(local_path)

        if not snapshot.get("commit"):
            return []

        current_commit = snapshot["commit"]
        if current_commit == last_seen:
            return []

        # Get new commits
        changes = self._collect_changes(
            project_id, local_path, last_seen, current_commit, snapshot.get("branch", "")
        )

        # Update last seen
        project["last_seen_commit"] = current_commit
        self.ledger.save()

        return changes

    def _collect_changes(
        self, project_id: str, local_path: str, last_seen: str | None,
        current_commit: str, branch: str,
    ) -> list[GitChange]:
        """Collect GitChange objects for new commits."""
        try:
            if last_seen:
                log_range = f"{last_seen}..{current_commit}"
            else:
                log_range = current_commit

            # Get commit log: hash|author|date|subject
            raw = _run_git(
                local_path, "log", log_range,
                "--format=%H|%an|%aI|%s", "--no-merges",
            )
            if not raw.strip():
                return []

            changes: list[GitChange] = []
            for line in raw.strip().splitlines():
                parts = line.split("|", 3)
                if len(parts) < 4:
                    continue
                commit_hash, author, timestamp, message = parts

                # Get changed files for this commit
                files_raw = _run_git(
                    local_path, "diff-tree", "--no-commit-id", "--name-only",
                    "-r", commit_hash,
                )
                changed_files = [f for f in files_raw.strip().splitlines() if f]

                # Get diff stat
                stat_raw = _run_git(
                    local_path, "diff", "--stat", f"{commit_hash}^", commit_hash,
                )

                change = GitChange(
                    project_id=project_id,
                    commit_hash=commit_hash,
                    commit_message=message,
                    author=author,
                    timestamp=timestamp,
                    changed_files=changed_files,
                    diff_stat=stat_raw[:2000],
                    significance=0.0,
                    branch=branch,
                )
                change.significance = self.score_significance(change)
                changes.append(change)

            return changes
        except Exception as e:
            logger.error(f"Error collecting changes: {e}")
            return []

    def score_significance(self, change: GitChange) -> float:
        """Score a change's significance from 0.0 to 1.0."""
        score = 0.0

        # Commit message keywords
        msg_lower = change.commit_message.lower()
        for kw in SIGNIFICANT_KEYWORDS:
            if kw.lower() in msg_lower:
                score += 0.3
                break

        # Changed file count (more files = more significant)
        n_files = len(change.changed_files)
        if n_files >= 10:
            score += 0.2
        elif n_files >= 5:
            score += 0.1

        # Critical file patterns
        critical_patterns = [
            r"\.env$", r"config\.", r"schema\.", r"migration",
            r"^api/", r"^public/", r"^src/main",
        ]
        for f in change.changed_files:
            for pat in critical_patterns:
                if re.search(pat, f, re.I):
                    score += 0.15
                    break

        # Merge commits
        if change.commit_message.startswith("Merge "):
            score += 0.2

        return min(1.0, score)

    def should_analyze(self, change: GitChange, threshold: float = 0.5) -> bool:
        """Return True if a change is significant enough to analyze."""
        return change.significance >= threshold

    def create_analysis_task(self, change: GitChange) -> Any | None:
        """Create a Task for a high-significance change."""
        if not self.should_analyze(change):
            return None

        # Truncate for task description
        msg = change.commit_message[:200]
        files_preview = ", ".join(change.changed_files[:5])

        task = self.tasks.create_task(
            goal=f"Analyze commit {change.commit_hash[:8]} in {change.project_id}",
            objective=f"Review commit '{msg}' (files: {files_preview}). "
                     f"Assess impact on project state and update drift.md if warranted.",
            project_id=change.project_id,
            priority=change.significance,
            estimated_cost=0.01,
        )
        return task


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _run_git(path: str, *args: str) -> str:
    """Run a git command, return stdout. Raises on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=Path(path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return ""


def _extract_components(changed_files: list[str]) -> list[str]:
    """Extract top-level directories from changed files."""
    components: set[str] = set()
    for f in changed_files:
        parts = f.split("/")
        if len(parts) > 1:
            components.add(parts[0])
        elif f.endswith(".py"):
            components.add("root")
    return sorted(components)


def _is_commit_significant(message: str, files: list[str]) -> bool:
    """Check if a commit message or file list suggests significance."""
    msg_lower = message.lower()
    return any(kw.lower() in msg_lower for kw in SIGNIFICANT_KEYWORDS)


def _format_diff_for_analysis(change: GitChange, max_chars: int = 3000) -> str:
    """Create a bounded summary of a change for model consumption."""
    msg = change.commit_message[:300]
    files = change.changed_files[:20]
    lines = [
        f"Project: {change.project_id}",
        f"Commit: {change.commit_hash[:12]}",
        f"Author: {change.author}",
        f"Branch: {change.branch}",
        f"Message: {msg}",
        f"Changed files ({len(change.changed_files)}):",
    ]
    for f in files:
        lines.append(f"  - {f}")
    if len(change.changed_files) > 20:
        lines.append(f"  ... and {len(change.changed_files) - 20} more")
    if change.diff_stat:
        lines.append("Diff stat:")
        lines.append(change.diff_stat[:1000])

    text = "\n".join(lines)
    return text[:max_chars]
