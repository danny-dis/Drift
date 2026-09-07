"""Tests for drift/attention.py — attention economy and compute-budget engine."""
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from drift.attention import (
    Candidate,
    BudgetTracker,
    AttentionEconomy,
    score_candidate,
    generate_candidates,
    select_best_candidate,
)
from drift.organism import DriftLedger, Project
from drift.task import TaskStore
from drift.receipt import ReceiptStore, ContextReceipt
from drift.memory import MemoryStream


# ---------------------------------------------------------------------------
# Score candidate
# ---------------------------------------------------------------------------

class TestScoreCandidate:
    def test_high_priority_cheap_task_scores_high(self):
        c = Candidate(
            source="git",
            description="Analyze critical commit",
            base_priority=0.9,
            novelty=0.8,
            staleness=0.7,
            estimated_cost=0.001,
        )
        score = score_candidate(c)
        assert score > 0.5

    def test_low_priority_expensive_task_scores_low(self):
        c = Candidate(
            source="reflection",
            description="Reflect on memories",
            base_priority=0.1,
            novelty=0.1,
            staleness=0.1,
            estimated_cost=0.10,
        )
        score = score_candidate(c)
        assert score < 0.2

    def test_cost_penalty_reduces_score(self):
        cheap = Candidate(source="t", description="t", base_priority=0.5, estimated_cost=0.001)
        expensive = Candidate(source="t", description="t", base_priority=0.5, estimated_cost=0.05)
        assert score_candidate(cheap) > score_candidate(expensive)

    def test_zero_cost_task_not_penalized(self):
        c = Candidate(source="t", description="t", base_priority=0.5, estimated_cost=0.0)
        score = score_candidate(c)
        # Should be positive (importance * 0.3 + novelty * 0.2 + ...)
        assert score > 0

    def test_clamps_values(self):
        c = Candidate(source="t", description="t", base_priority=2.0, novelty=-1.0)
        # Should not raise, values clamped
        score = score_candidate(c)
        assert isinstance(score, float)


# ---------------------------------------------------------------------------
# Budget tracker
# ---------------------------------------------------------------------------

class TestBudgetTracker:
    def test_initial_budget_not_exhausted(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        assert not budget.budget_exhausted()

    def test_can_afford_within_budget(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        assert budget.can_afford(0.01)

    def test_records_spend(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(0.5)
        assert budget.daily_spend() == 0.5
        assert budget.weekly_spend() == 0.5

    def test_budget_exhausted_after_overspend(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(100.0)
        assert budget.budget_exhausted()

    def test_daily_reset(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(0.5)
        budget.reset_daily()
        assert budget.daily_spend() == 0.0
        assert budget.weekly_spend() == 0.5

    def test_weekly_reset(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(0.5)
        budget.reset_weekly()
        assert budget.weekly_spend() == 0.0

    def test_high_priority_uses_emergency_reserve(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        # Spend up to the daily limit
        budget.record_spend(budget.get_daily_budget())
        # Normal task should be rejected
        assert not budget.can_afford(0.01, is_high_priority=False)
        # High-priority task can use emergency reserve (10%)
        assert budget.can_afford(0.01, is_high_priority=True)

    def test_zero_cost_always_allowed(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(100.0)
        assert budget.can_afford(0.0)

    def test_total_spend_from_receipts(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        store.save_receipt(ContextReceipt("t1", 7000, 1750, estimated_cost=0.01))
        store.save_receipt(ContextReceipt("t2", 6500, 1625, estimated_cost=0.02))
        budget = BudgetTracker(store)
        assert budget.total_spend() == 0.03


# ---------------------------------------------------------------------------
# Select best candidate
# ---------------------------------------------------------------------------

class TestSelectBestCandidate:
    def test_selects_highest_scoring(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        candidates = [
            Candidate(source="t", description="low", base_priority=0.1, estimated_cost=0.01),
            Candidate(source="t", description="high", base_priority=0.9, estimated_cost=0.01),
            Candidate(source="t", description="mid", base_priority=0.5, estimated_cost=0.01),
        ]
        best = select_best_candidate(candidates, budget)
        assert best.description == "high"

    def test_none_when_empty(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        assert select_best_candidate([], budget) is None

    def test_skips_over_budget(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(100.0)  # exhaust budget
        candidates = [
            Candidate(source="t", description="expensive", base_priority=0.9, estimated_cost=0.05),
        ]
        assert select_best_candidate(candidates, budget) is None

    def test_zero_cost_selected_when_budget_exhausted(self, tmp_path):
        store = ReceiptStore(str(tmp_path))
        budget = BudgetTracker(store)
        budget.record_spend(100.0)
        candidates = [
            Candidate(source="t", description="free", base_priority=0.5, estimated_cost=0.0),
        ]
        best = select_best_candidate(candidates, budget)
        assert best.description == "free"


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

class TestGenerateCandidates:
    def _make_brain(self, tmp_path):
        """Create a minimal Brain-like object for testing."""
        env_path = str(tmp_path / "env")
        Path(env_path).mkdir(parents=True, exist_ok=True)
        brain = MagicMock()
        brain.env_path = env_path
        brain.ledger = DriftLedger(env_path)
        brain.tasks = TaskStore(env_path)
        brain.receipts = ReceiptStore(env_path)
        brain.stream = MemoryStream(env_path)
        brain._inbox_pending = []
        brain.watcher = None  # explicitly None so getattr works
        return brain

    def test_generates_idea_candidates(self, tmp_path):
        brain = self._make_brain(tmp_path)
        brain.ledger.add_idea("Build a graph database", ["graph", "database"])
        candidates = generate_candidates(brain)
        assert len(candidates) >= 1
        assert any(c.source == "unqualified_idea" for c in candidates)

    def test_generates_stalled_task_candidates(self, tmp_path):
        brain = self._make_brain(tmp_path)
        t = brain.tasks.create_task("work", "do it", priority=0.7)
        # Transition through valid phases to research, then block
        brain.tasks.update_task(t.id, phase="understand")
        brain.tasks.update_task(t.id, phase="connect")
        brain.tasks.update_task(t.id, phase="research")
        brain.tasks.update_task(t.id, status="blocked")
        candidates = generate_candidates(brain)
        assert any(c.source == "stalled_task" for c in candidates)

    def test_generates_stale_project_candidates(self, tmp_path):
        brain = self._make_brain(tmp_path)
        old_time = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        brain.ledger.add_project(Project(
            id="proj-old", name="Old Project", repo="",
            last_round=old_time,
        ))
        candidates = generate_candidates(brain)
        assert any(c.source == "project_stale" for c in candidates)

    def test_generates_inbox_candidates(self, tmp_path):
        brain = self._make_brain(tmp_path)
        brain._inbox_pending = [{"name": "note.txt", "content": "hello"}]
        candidates = generate_candidates(brain)
        assert any(c.source == "inbox" for c in candidates)

    def test_deduplication(self, tmp_path):
        brain = self._make_brain(tmp_path)
        brain.ledger.add_idea("Test idea", ["test"])
        # Generate twice — should get same candidates (dedup within single call)
        c1 = generate_candidates(brain)
        c2 = generate_candidates(brain)
        # Both should have the idea candidate
        assert len(c1) == len(c2)

    def test_no_candidates_when_empty(self, tmp_path):
        brain = self._make_brain(tmp_path)
        candidates = generate_candidates(brain)
        assert candidates == []


# ---------------------------------------------------------------------------
# AttentionEconomy integration
# ---------------------------------------------------------------------------

class TestAttentionEconomy:
    def _make_brain(self, tmp_path):
        env_path = str(tmp_path / "env")
        Path(env_path).mkdir(parents=True, exist_ok=True)
        brain = MagicMock()
        brain.env_path = env_path
        brain.ledger = DriftLedger(env_path)
        brain.tasks = TaskStore(env_path)
        brain.receipts = ReceiptStore(env_path)
        brain.stream = MemoryStream(env_path)
        brain._inbox_pending = []
        brain.watcher = None
        return brain

    def test_generate_and_select_returns_candidate(self, tmp_path):
        brain = self._make_brain(tmp_path)
        brain.ledger.add_idea("Test idea", ["test"])
        economy = AttentionEconomy(brain.receipts)
        result = economy.generate_and_select(brain)
        assert result is not None

    def test_create_task_from_candidate(self, tmp_path):
        brain = self._make_brain(tmp_path)
        economy = AttentionEconomy(brain.receipts)
        candidate = Candidate(
            source="inbox",
            description="Process file",
            project_id=None,
            base_priority=0.7,
            estimated_cost=0.01,
        )
        task = economy.create_task_from_candidate(brain, candidate)
        assert task is not None
        assert task.goal == "Process file"

    def test_create_task_updates_project_last_round(self, tmp_path):
        brain = self._make_brain(tmp_path)
        brain.ledger.add_project(Project(id="p1", name="Proj", repo=""))
        economy = AttentionEconomy(brain.receipts)
        candidate = Candidate(
            source="git",
            description="Analyze",
            project_id="p1",
            base_priority=0.7,
            estimated_cost=0.01,
        )
        economy.create_task_from_candidate(brain, candidate)
        project = brain.ledger.data["projects"][0]
        assert project.get("last_round") is not None

    def test_get_status(self, tmp_path):
        brain = self._make_brain(tmp_path)
        economy = AttentionEconomy(brain.receipts)
        status = economy.get_status()
        assert "daily_budget" in status
        assert "daily_remaining" in status
        assert "weekly_budget" in status
        assert "weekly_remaining" in status
        assert "total_spend" in status

    def test_budget_exhausted_returns_none(self, tmp_path):
        brain = self._make_brain(tmp_path)
        brain.ledger.add_idea("Test idea", ["test"])
        economy = AttentionEconomy(brain.receipts)
        # Exhaust budget
        economy.budget.record_spend(100.0)
        result = economy.generate_and_select(brain)
        # Should return None since the idea candidate has estimated_cost > 0
        assert result is None
