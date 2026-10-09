"""Attention economy and compute-budget engine for Drift (Phase 3).

Drift treats model access as a scarce cognitive resource. This module scores
candidate tasks by expected value / estimated cost, enforces budgets,
prevents starvation of low-priority projects, and avoids duplicate work.

All logic is deterministic and cheap — no model calls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drift.config import config

logger = logging.getLogger("drift.attention")


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    """A potential task generated from a signal in the environment."""
    source: str          # "git", "inbox", "stalled_task", "unqualified_idea", "project_stale", "reflection"
    description: str     # short human-readable description
    project_id: str | None = None
    base_priority: float = 0.5   # 0-1, signal-specific importance
    novelty: float = 0.5         # 0-1, how new/unique vs recent work
    staleness: float = 0.5       # 0-1, time since project last got attention
    estimated_cost: float = 0.0  # in dollars
    owner_interest: float = 0.0  # 0-1, learned from owner interactions
    created_at: float = field(default_factory=time.time)
    dedup_key: str = ""          # unique key for deduplication

    def __post_init__(self) -> None:
        self.base_priority = max(0.0, min(1.0, self.base_priority))
        self.novelty = max(0.0, min(1.0, self.novelty))
        self.staleness = max(0.0, min(1.0, self.staleness))
        self.owner_interest = max(0.0, min(1.0, self.owner_interest))


# ---------------------------------------------------------------------------
# Attention scoring
# ---------------------------------------------------------------------------

# Weights for the attention score. Must sum to <= 1.0 for interpretability.
_W_IMPORTANCE = 0.30
_W_NOVELTY = 0.20
_W_STALENESS = 0.20
_W_OWNER = 0.15
_W_COST = 0.15


def score_candidate(candidate: Candidate) -> float:
    """Compute an attention score for a candidate.

    Higher = more worth doing now. Score is roughly in [0, 1] but can
    slightly exceed 1.0 if all factors are maxed.

    The cost term penalizes expensive tasks — a $0.10 task needs ~2x the
    raw value of a $0.01 task to get the same score.
    """
    # Cost penalty: normalized so $0 = 0.0, $0.05+ = 1.0
    cost_penalty = min(1.0, candidate.estimated_cost / 0.05)

    score = (
        _W_IMPORTANCE * candidate.base_priority
        + _W_NOVELTY * candidate.novelty
        + _W_STALENESS * candidate.staleness
        + _W_OWNER * candidate.owner_interest
        - _W_COST * cost_penalty
    )
    return round(score, 4)


# ---------------------------------------------------------------------------
# Budget tracking
# ---------------------------------------------------------------------------

class BudgetTracker:
    """Track model spend against configured budgets.

    Uses ReceiptStore to sum estimated_cost from receipts. Budgets are
    configured via config.yaml / env vars.
    """

    def __init__(self, receipt_store: Any) -> None:
        self.receipt_store = receipt_store
        self._last_weekly_reset: float = time.time()
        self._last_daily_reset: float = time.time()
        self._weekly_spend: float = 0.0
        self._daily_spend: float = 0.0

    def get_daily_budget(self) -> float:
        return float(config.get("attention_daily_budget", 1.0))

    def get_weekly_budget(self) -> float:
        return float(config.get("attention_weekly_budget", 5.0))

    def get_emergency_reserve(self) -> float:
        """Fraction of budget reserved for high-priority discoveries."""
        return float(config.get("attention_emergency_reserve", 0.10))

    def total_spend(self) -> float:
        """Sum estimated_cost across all receipts."""
        return self.receipt_store.get_total_estimated_cost()

    def daily_spend(self) -> float:
        """Spend since last daily reset."""
        return self._daily_spend

    def weekly_spend(self) -> float:
        """Spend since last weekly reset."""
        return self._weekly_spend

    def daily_remaining(self) -> float:
        return max(0.0, self.get_daily_budget() - self._daily_spend)

    def weekly_remaining(self) -> float:
        return max(0.0, self.get_weekly_budget() - self._weekly_spend)

    def budget_exhausted(self) -> bool:
        """True if both daily and weekly budgets are spent."""
        return self.daily_remaining() <= 0 and self.weekly_remaining() <= 0

    def can_afford(self, estimated_cost: float, is_high_priority: bool = False) -> bool:
        """Check if a task of given cost fits within budget.

        High-priority tasks can draw from the emergency reserve.
        """
        if estimated_cost <= 0:
            return True  # zero-cost tasks always allowed
        reserve = self.get_emergency_reserve()
        daily_cap = self.get_daily_budget() * (1.0 + reserve if is_high_priority else 1.0)
        weekly_cap = self.get_weekly_budget() * (1.0 + reserve if is_high_priority else 1.0)
        return (
            self._daily_spend + estimated_cost <= daily_cap
            and self._weekly_spend + estimated_cost <= weekly_cap
        )

    def record_spend(self, cost: float) -> None:
        """Record a spend (called after a model call)."""
        self._daily_spend += cost
        self._weekly_spend += cost

    def reset_daily(self) -> None:
        self._daily_spend = 0.0
        self._last_daily_reset = time.time()

    def reset_weekly(self) -> None:
        self._weekly_spend = 0.0
        self._last_weekly_reset = time.time()


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def generate_candidates(brain: Any) -> list[Candidate]:
    """Generate candidate tasks from all available signals.

    Signals: GitWatcher changes, stalled/blocked tasks, unqualified ideas,
    stale projects, inbox files, reflection triggers.
    """
    candidates: list[Candidate] = []
    seen_dedup: set[str] = set()

    # 1. GitWatcher changes (if watcher is available)
    watcher = getattr(brain, 'watcher', None)
    if watcher is not None and watcher.get_watched_projects():
        try:
            changes = watcher.scan_all()
            for change in changes:
                dedup_key = f"git:{change.project_id}:{change.commit_hash}"
                if dedup_key in seen_dedup:
                    continue
                seen_dedup.add(dedup_key)
                if watcher.should_analyze(change):
                    candidates.append(Candidate(
                        source="git",
                        description=f"Analyze commit {change.commit_hash[:8]}: {change.commit_message[:80]}",
                        project_id=change.project_id,
                        base_priority=change.significance,
                        novelty=0.7,  # new commits are novel
                        staleness=0.5,
                        estimated_cost=0.01,
                        dedup_key=dedup_key,
                    ))
        except Exception as e:
            logger.warning("GitWatcher scan failed during candidate generation: %s", e)

    # 2. Stalled/blocked tasks
    for task in brain.tasks.list_tasks():
        if task.status == "blocked":
            dedup_key = f"stalled:{task.id}"
            if dedup_key not in seen_dedup:
                seen_dedup.add(dedup_key)
                candidates.append(Candidate(
                    source="stalled_task",
                    description=f"Resume blocked task: {task.goal}",
                    project_id=task.project_id,
                    base_priority=task.priority * 0.8,
                    novelty=0.3,  # already being worked on
                    staleness=0.6,
                    estimated_cost=task.estimated_cost or 0.01,
                    dedup_key=dedup_key,
                ))

    # 3. Unqualified ideas
    for idea in brain.ledger.data.get("ideas", []):
        if idea.get("status", "captured") == "captured":
            idea_id = idea.get("id", "")
            dedup_key = f"idea:{idea_id}"
            if dedup_key not in seen_dedup:
                seen_dedup.add(dedup_key)
                candidates.append(Candidate(
                    source="unqualified_idea",
                    description=f"Qualify idea: {idea.get('text', '')[:80]}",
                    project_id=None,
                    base_priority=0.4,
                    novelty=0.6,
                    staleness=0.4,
                    estimated_cost=0.005,
                    dedup_key=dedup_key,
                ))

    # 4. Stale projects (not recently checked)
    now = time.time()
    for project in brain.ledger.data.get("projects", []):
        pid = project.get("id", "")
        last_round = project.get("last_round")
        staleness_score = 0.5
        if last_round:
            try:
                last_time = datetime.fromisoformat(last_round.replace("Z", "+00:00")).timestamp()
                hours_ago = max(0, (now - last_time) / 3600)
                # 0 hours = 0.0, 72+ hours = 1.0
                staleness_score = min(1.0, hours_ago / 72.0)
            except (ValueError, TypeError):
                pass
        if staleness_score >= 0.5:
            dedup_key = f"stale_project:{pid}"
            if dedup_key not in seen_dedup:
                seen_dedup.add(dedup_key)
                candidates.append(Candidate(
                    source="project_stale",
                    description=f"Check stale project: {project.get('name', pid)}",
                    project_id=pid,
                    base_priority=0.3 + 0.3 * staleness_score,
                    novelty=0.2,
                    staleness=staleness_score,
                    estimated_cost=0.01,
                    dedup_key=dedup_key,
                ))

    # 5. Inbox files (pending)
    if brain._inbox_pending:
        for f in brain._inbox_pending:
            dedup_key = f"inbox:{f.get('name', '')}"
            if dedup_key not in seen_dedup:
                seen_dedup.add(dedup_key)
                candidates.append(Candidate(
                    source="inbox",
                    description=f"Process inbox file: {f.get('name', 'unknown')}",
                    project_id=None,
                    base_priority=0.7,  # owner-provided = high priority
                    novelty=0.8,
                    staleness=0.9,
                    estimated_cost=0.01,
                    dedup_key=dedup_key,
                ))

    # 6. Reflection trigger
    if brain.stream and brain.stream.should_reflect():
        dedup_key = "reflection:trigger"
        if dedup_key not in seen_dedup:
            seen_dedup.add(dedup_key)
            candidates.append(Candidate(
                source="reflection",
                description="Reflect on recent memories and extract insights",
                project_id=None,
                base_priority=0.5,
                novelty=0.5,
                staleness=0.5,
                estimated_cost=0.005,
                dedup_key=dedup_key,
            ))

    return candidates


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_best_candidate(
    candidates: list[Candidate],
    budget: BudgetTracker,
) -> Candidate | None:
    """Select the highest-scoring candidate that fits the budget.

    High-priority candidates (base_priority >= 0.8) can use emergency reserve.
    """
    if not candidates:
        return None

    scored = [(score_candidate(c), c) for c in candidates]
    scored.sort(key=lambda x: x[0], reverse=True)

    for score, candidate in scored:
        is_high_priority = candidate.base_priority >= 0.8
        if budget.can_afford(candidate.estimated_cost, is_high_priority=is_high_priority):
            return candidate

    # Nothing fits budget — return the best zero-cost candidate if any
    for score, candidate in scored:
        if candidate.estimated_cost <= 0:
            return candidate

    return None


# ---------------------------------------------------------------------------
# AttentionEconomy — ties it together for Brain
# ---------------------------------------------------------------------------

class AttentionEconomy:
    """High-level interface for Brain to use the attention economy.

    Wraps BudgetTracker and provides methods to create tasks from
    attention-scored candidates.
    """

    def __init__(self, receipt_store: Any) -> None:
        self.budget = BudgetTracker(receipt_store)

    def generate_and_select(self, brain: Any) -> Candidate | None:
        """Generate candidates and return the best one within budget."""
        candidates = generate_candidates(brain)
        if not candidates:
            return None
        return select_best_candidate(candidates, self.budget)

    def create_task_from_candidate(self, brain: Any, candidate: Candidate) -> Any:
        """Create a Task from a selected candidate."""
        task = brain.tasks.create_task(
            goal=candidate.description[:200],
            objective=candidate.description,
            project_id=candidate.project_id,
            priority=candidate.base_priority,
            estimated_cost=candidate.estimated_cost,
        )
        # Update project's last_round if applicable
        if candidate.project_id:
            project = next(
                (p for p in brain.ledger.data.get("projects", [])
                 if p["id"] == candidate.project_id),
                None,
            )
            if project:
                project["last_round"] = datetime.now(timezone.utc).isoformat()
                brain.ledger.save()
        return task

    def get_status(self) -> dict[str, float]:
        """Return budget telemetry for broadcasting."""
        return {
            "daily_budget": self.budget.get_daily_budget(),
            "daily_remaining": self.budget.daily_remaining(),
            "weekly_budget": self.budget.get_weekly_budget(),
            "weekly_remaining": self.budget.weekly_remaining(),
            "total_spend": self.budget.total_spend(),
        }
