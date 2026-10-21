"""Regression coverage for attention budget durability and safe task creation."""

import json
from pathlib import Path
from unittest.mock import MagicMock

from drift.attention import AttentionEconomy, BudgetTracker, Candidate, generate_candidates
from drift.config import config
from drift.memory import MemoryStream
from drift.organism import DriftLedger
from drift.receipt import ReceiptStore
from drift.task import TaskStore


class ReceiptWithoutPath:
    def get_total_estimated_cost(self):
        return 0.0


def make_brain(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    brain = MagicMock()
    brain.env_path = str(root)
    brain.ledger = DriftLedger(str(root))
    brain.tasks = TaskStore(str(root))
    brain.receipts = ReceiptStore(str(root))
    brain.stream = MemoryStream(str(root))
    brain._inbox_pending = []
    brain.watcher = None
    return brain


def test_receipt_without_path_uses_configured_environment_path(tmp_path, monkeypatch):
    env = tmp_path / "configured-environment"
    monkeypatch.setitem(config, "environment_path", str(env))

    first = BudgetTracker(ReceiptWithoutPath())
    first.record_spend(0.5)
    restarted = BudgetTracker(ReceiptWithoutPath())

    assert restarted.daily_spend() == 0.5
    assert first._path == str(env / BudgetTracker.FILENAME)
    assert (env / BudgetTracker.FILENAME).is_file()


def test_budget_persistence_isolated_by_environment_root(tmp_path, monkeypatch):
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setitem(config, "environment_path", str(root_a))
    BudgetTracker(ReceiptWithoutPath()).record_spend(0.75)

    monkeypatch.setitem(config, "environment_path", str(root_b))
    isolated = BudgetTracker(ReceiptWithoutPath())

    assert isolated.daily_spend() == 0.0
    assert isolated.weekly_spend() == 0.0
    assert (root_a / BudgetTracker.FILENAME).is_file()
    assert not (root_b / BudgetTracker.FILENAME).exists()


def test_corrupt_budget_fails_closed_for_paid_admission(tmp_path, monkeypatch):
    monkeypatch.setitem(config, "environment_path", str(tmp_path))
    budget_file = tmp_path / BudgetTracker.FILENAME
    budget_file.write_text("{ definitely not valid json", encoding="utf-8")

    budget = BudgetTracker(ReceiptWithoutPath())

    assert not budget.can_afford(0.001)
    assert budget.daily_remaining() == 0.0
    assert budget.weekly_remaining() == 0.0


def test_blocked_tasks_are_not_automatically_rescheduled(tmp_path):
    brain = make_brain(tmp_path)
    task = brain.tasks.create_task("owner approval", "sensitive work", priority=0.8)
    brain.tasks.update_task(task.id, phase="understand")
    brain.tasks.update_task(task.id, phase="blocked", status="blocked")

    assert not any(candidate.source == "stalled_task" for candidate in generate_candidates(brain))
    assert brain.tasks.get_next_task() is None


def test_idea_already_referenced_by_task_is_not_regenerated(tmp_path):
    brain = make_brain(tmp_path)
    brain.ledger.add_idea("Build a durable event graph", ["events", "graph"])
    brain.tasks.create_task(
        "Build event graph", "Please BUILD A DURABLE EVENT GRAPH for the prototype"
    )

    assert not any(candidate.source == "unqualified_idea" for candidate in generate_candidates(brain))


def test_candidate_task_persists_next_action_and_dedup_key(tmp_path):
    brain = make_brain(tmp_path)
    from dataclasses import asdict
    from drift.organism import Idea
    brain.ledger.mutate(lambda data: data['ideas'].append(
        asdict(Idea(id='idea-123', text='durable event graph'))))
    candidate = Candidate(
        source="unqualified_idea",
        description="Qualify idea: durable event graph",
        dedup_key="idea:idea-123",
    )
    task = AttentionEconomy(brain.receipts).create_task_from_candidate(brain, candidate)
    restarted = TaskStore(str(tmp_path)).get_task(task.id)

    assert restarted.next_action == "Qualify idea: durable event graph"
    assert restarted.last_evidence == "attention_dedup_key=idea:idea-123"


def test_malformed_numeric_budget_data_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setitem(config, "environment_path", str(tmp_path))
    budget_file = tmp_path / BudgetTracker.FILENAME
    budget_file.write_text(json.dumps({"day": "2099-01-01", "week": "2099-W01",
                                       "daily": "NaN", "weekly": -2}), encoding="utf-8")

    budget = BudgetTracker(ReceiptWithoutPath())

    assert not budget.can_afford(0.001)
