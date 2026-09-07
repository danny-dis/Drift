"""Durable task state management for Drift's cognitive kernel.

Tasks are resumable and idempotent: every mutation rewrites the full state
atomically (tmp + replace) so a crash mid-write can never corrupt the store.
The cognitive loop calls ``get_next_task`` to pick the highest-priority
incomplete task, works it, then ``update_task`` to checkpoint progress.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("drift.task")

# Phases flow left-to-right; any phase can enter blocked and return.
PHASES: list[str] = [
    "capture",
    "understand",
    "connect",
    "research",
    "verify",
    "synthesize",
    "qualify",
    "monitor",
    "complete",
    "blocked",
]

# Forward transitions: each phase may advance to the next, or go to blocked.
_FORWARD: dict[str, str] = {
    PHASES[i]: PHASES[i + 1] for i in range(len(PHASES) - 2)  # everything except complete/blocked
}

# Blocked tasks may return to the phase they came from (tracked via _prev_phase).
_BLOCKED_RETURN = "blocked"


@dataclass
class Task:
    """One unit of cognitive work. Serializable, comparable, resumable."""

    id: str
    goal: str
    objective: str
    project_id: str | None = None
    phase: str = "capture"
    status: str = "pending"
    progress: float = 0.0
    blockers: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    last_evidence: str = ""
    next_action: str = ""
    priority: float = 0.5
    estimated_cost: float = 0.0
    budget_remaining: float = 0.0
    attempt_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Internal: remembers which phase a blocked task came from so it can resume.
    _prev_phase: str = "capture"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        # Only accept known fields so schema drift is loud, not silent.
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


def can_transition(task: Task, new_phase: str) -> bool:
    """Return True if moving task.phase -> new_phase is allowed.

    Rules:
      - Forward: capture -> understand -> ... -> monitor -> complete.
      - Any non-blocked phase may enter ``blocked``.
      - Blocked may return to the phase it was in before blocking.
      - complete is terminal (no outgoing transitions).
    """
    if new_phase not in PHASES:
        return False
    current = task.phase
    if current == new_phase:
        return True  # idempotent: staying put is always valid
    if current == "complete":
        return False
    if current == "blocked":
        return new_phase == task._prev_phase
    if new_phase == "blocked":
        return True
    return _FORWARD.get(current) == new_phase


class TaskStore:
    """Atomic, file-backed task store.

    All mutations go through ``save`` which writes a temp file then renames,
    so an interrupted write leaves the original intact. A lock guards
    concurrent access within a single process.
    """

    def __init__(self, env_path: str):
        self.root = Path(env_path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tasks.json"
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._next_id: int = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.error("Failed to load tasks.json: %s", e)
            return
        for item in raw.get("tasks", []):
            task = Task.from_dict(item)
            self._tasks[task.id] = task
        if self._tasks:
            max_id = max(int(t.id.split("-")[1]) for t in self._tasks.values())
            self._next_id = max_id + 1
        logger.info("Loaded %d tasks from %s", len(self._tasks), self.path)

    def save(self) -> None:
        """Atomic write: tmp + replace, same pattern as DriftLedger.save."""
        payload = {
            "schema": 1,
            "tasks": [t.to_dict() for t in self._tasks.values()],
        }
        data = json.dumps(payload, indent=2, ensure_ascii=False)
        fd, tmp_path = tempfile.mkstemp(
            prefix=".tasks-", suffix=".tmp", dir=str(self.root)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, self.path)
        except Exception:
            # Clean up the temp file if replace failed.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def create_task(
        self,
        goal: str,
        objective: str,
        project_id: str | None = None,
        priority: float = 0.5,
        estimated_cost: float = 0.0,
    ) -> Task:
        """Create a new task with a unique id and current timestamps."""
        with self._lock:
            task_id = f"task-{self._next_id:06d}"
            self._next_id += 1
            now = datetime.now(timezone.utc).isoformat()
            task = Task(
                id=task_id,
                goal=goal,
                objective=objective,
                project_id=project_id,
                priority=priority,
                estimated_cost=estimated_cost,
                budget_remaining=estimated_cost,
                created_at=now,
                updated_at=now,
            )
            self._tasks[task_id] = task
            self.save()
            logger.info("Created task %s: %s", task_id, goal[:60])
            return task

    def get_task(self, task_id: str) -> Task | None:
        """Return the task by id, or None."""
        return self._tasks.get(task_id)

    def update_task(self, task_id: str, **kwargs: Any) -> Task:
        """Partial update. Auto-refreshes ``updated_at``. Returns the updated task.

        Raises KeyError if the task does not exist.
        Raises ValueError if a phase change violates the transition rules.
        """
        with self._lock:
            task = self._tasks[task_id]
            if "phase" in kwargs and not can_transition(task, kwargs["phase"]):
                raise ValueError(
                    f"Invalid phase transition: {task.phase} -> {kwargs['phase']}"
                )
            # Track previous phase when entering blocked.
            if kwargs.get("phase") == "blocked":
                kwargs["_prev_phase"] = task.phase
            for key, value in kwargs.items():
                if key == "id":
                    continue  # never mutate identity
                if not hasattr(task, key):
                    raise AttributeError(f"Task has no field {key!r}")
                setattr(task, key, value)
            task.updated_at = datetime.now(timezone.utc).isoformat()
            self.save()
            return task

    def list_tasks(
        self,
        status: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[Task]:
        """List tasks, optionally filtered by status and/or project.

        Results are sorted by priority (desc), then created_at (asc) so the
        most important, oldest-queued tasks surface first.
        """
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if project_id is not None:
            tasks = [t for t in tasks if t.project_id == project_id]
        tasks.sort(key=lambda t: (-t.priority, t.created_at))
        return tasks[:limit]

    def get_next_task(self) -> Task | None:
        """Highest-priority incomplete task.

        Excludes tasks whose status is ``complete`` or ``blocked``.
        Ties broken by created_at (oldest first) so work is FIFO within a
        priority band.
        """
        candidates = [
            t for t in self._tasks.values()
            if t.status not in ("complete", "blocked")
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda t: (-t.priority, t.created_at))
        return candidates[0]

    def reset_attempts(self, task_id: str) -> Task:
        """Reset attempt_count to 0. Used by retry logic after a backoff."""
        with self._lock:
            task = self._tasks[task_id]
            task.attempt_count = 0
            task.updated_at = datetime.now(timezone.utc).isoformat()
            self.save()
            return task