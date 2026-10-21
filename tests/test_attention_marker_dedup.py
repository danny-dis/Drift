from types import SimpleNamespace

from drift.attention import AttentionEconomy, generate_candidates
from drift.organism import DriftLedger
from drift.receipt import ReceiptStore
from drift.task import TaskStore


def test_long_idea_candidate_is_not_recreated_after_block_and_restart(tmp_path):
    brain = SimpleNamespace(
        env_path=str(tmp_path),
        ledger=DriftLedger(str(tmp_path)), tasks=TaskStore(str(tmp_path)),
        watcher=None, stream=None, _inbox_pending=[],
    )
    brain.ledger.add_idea("A long owner original with distinct details. " * 12, [])
    candidates = generate_candidates(brain)
    assert len(candidates) == 1
    task = AttentionEconomy(ReceiptStore(str(tmp_path))).create_task_from_candidate(brain, candidates[0])
    brain.tasks.update_task(task.id, phase="blocked", status="blocked")
    brain.tasks = TaskStore(str(tmp_path))
    assert not any(c.source == "unqualified_idea" for c in generate_candidates(brain))
    assert len(brain.tasks.list_tasks()) == 1
