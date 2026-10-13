from types import SimpleNamespace

from drift.attention import AttentionEconomy, generate_candidates
from drift.organism import DriftLedger
from drift.receipt import ReceiptStore
from drift.task import TaskStore


def make_brain(root):
    return SimpleNamespace(
        ledger=DriftLedger(str(root)),
        tasks=TaskStore(str(root)),
        watcher=None,
        stream=None,
        _inbox_pending=[],
    )


def test_linked_blocked_capture_does_not_spawn_qualification_task(tmp_path):
    brain = make_brain(tmp_path)
    idea = brain.ledger.add_idea(
        "My scattered original needs to remain safe when the provider is unavailable.",
        [],
    )
    task = brain.tasks.create_task("Understand captured thought abc", "Organize the original")
    brain.tasks.update_task(task.id, idea_id=idea.id, phase="blocked", status="blocked")
    assert not any(c.source == "unqualified_idea" for c in generate_candidates(brain))
