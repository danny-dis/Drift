"""Owner approval repairs the canonical projection without replacing originals."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.intake import stage_captures
from drift.outcomes import block_task
from drift.server import create_app


def ready(root):
    brain = Brain({'name': 'approval'}, str(root))
    brain._init_stores()
    return brain, TestClient(create_app({'approval': brain}))


def blocked_capture(root, text='  Original thought\n\t'):
    brain, client = ready(root)
    store = CaptureStore(root)
    capture = store.capture(text)['capture']
    stage_captures(brain)
    parts = sorted(brain.tasks.list_tasks(limit=100000), key=lambda t: t.part_index)
    for task in parts:
        block_task(brain, task, 'Owner review required')
        brain.tasks.update_task(task.id, attempt_count=4)
    store.finish(parts[0].id, 'needs_review', 'answers/partial.md', 'Retained partial summary')
    return brain, client, capture, parts


def metadata(root):
    with sqlite3.connect(root / 'captures.sqlite3') as db:
        return db.execute('SELECT text, idea_id, task_id, report_path, summary FROM captures').fetchone()


def test_approval_requeues_canonical_capture_without_losing_metadata(tmp_path):
    brain, client, capture, parts = blocked_capture(tmp_path)
    before = metadata(tmp_path)
    result = client.post(f'/api/ui/approvals/{parts[0].id}/approve')
    assert result.status_code == 200
    stored = CaptureStore(tmp_path).get(capture['id'])
    assert stored['status'] == 'queued'
    assert metadata(tmp_path) == before
    task = brain.tasks.get_task(parts[0].id)
    assert (task.status, task.phase, task.attempt_count, task.blockers) == ('pending', 'capture', 0, [])
    assert client.get(f"/api/ui/captures/{capture['id']}/insights").json()['status'] == 'queued'
    assert CaptureStore(tmp_path).list(status='needs_review')['total'] == 0


def test_multipart_approval_waits_for_every_blocked_sibling(tmp_path):
    brain, client, capture, parts = blocked_capture(tmp_path, 'Thought part. ' * 200)
    assert len(parts) > 1
    before = metadata(tmp_path)
    for task in parts[:-1]:
        assert client.post(f'/api/ui/approvals/{task.id}/approve').status_code == 200
        assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'needs_review'
    assert client.post(f'/api/ui/approvals/{parts[-1].id}/approve').status_code == 200
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'queued'
    assert metadata(tmp_path) == before
    assert len(brain.tasks.list_tasks()) == len(parts)


@pytest.mark.parametrize('error', [OSError, sqlite3.OperationalError])
@pytest.mark.parametrize('after_commit', [False, True])
def test_interrupted_capture_write_can_retry_same_approval_after_restart(tmp_path, monkeypatch, error, after_commit):
    brain, client, capture, parts = blocked_capture(tmp_path)
    before = metadata(tmp_path)
    write = CaptureStore.set_status

    def fail(store, capture_id, status):
        if after_commit:
            write(store, capture_id, status)
        raise error('fixture capture checkpoint interruption')

    with monkeypatch.context() as patch:
        patch.setattr(CaptureStore, 'set_status', fail)
        result = client.post(f'/api/ui/approvals/{parts[0].id}/approve')
        assert result.status_code == 503
    restarted, client = ready(tmp_path)
    task = restarted.tasks.get_task(parts[0].id)
    assert (task.status, task.attempt_count) == ('pending', 0)
    assert client.post(f'/api/ui/approvals/{task.id}/approve').status_code == 200
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'queued'
    assert metadata(tmp_path) == before
    assert len(restarted.tasks.list_tasks()) == 1


def test_failed_task_checkpoint_leaves_capture_blocked_and_retryable(tmp_path, monkeypatch):
    brain, client, capture, parts = blocked_capture(tmp_path)
    before = metadata(tmp_path)

    def fail(*args, **kwargs):
        raise OSError('fixture task checkpoint interruption')

    with monkeypatch.context() as patch:
        patch.setattr(brain.tasks, 'save', fail)
        assert client.post(f'/api/ui/approvals/{parts[0].id}/approve').status_code == 503
    restarted, client = ready(tmp_path)
    assert restarted.tasks.get_task(parts[0].id).status == 'blocked'
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'needs_review'
    assert metadata(tmp_path) == before
    assert client.post(f'/api/ui/approvals/{parts[0].id}/approve').status_code == 200


def test_restarted_reconciliation_keeps_processed_metadata_unchanged(tmp_path):
    from drift.outcomes import reconcile_capture_task
    brain, client, capture, parts = blocked_capture(tmp_path)
    assert client.post(f'/api/ui/approvals/{parts[0].id}/approve').status_code == 200
    brain._complete_report_task(parts[0], 'answers/finished.md')
    CaptureStore(tmp_path).finish(parts[0].id, 'processed', 'answers/finished.md', 'Final retained summary')
    before = metadata(tmp_path)
    restarted, _ = ready(tmp_path)
    reconcile_capture_task(restarted, restarted.tasks.get_task(parts[0].id))
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'processed'
    assert metadata(tmp_path) == before


def test_restart_reconciliation_repairs_projection_without_new_tasks(tmp_path):
    from drift.outcomes import reconcile_capture_task
    brain, _, capture, parts = blocked_capture(tmp_path, 'Thought part. ' * 200)
    before = metadata(tmp_path)
    brain.tasks.update_task(parts[0].id, status='pending', phase=parts[0]._prev_phase,
                            attempt_count=0, blockers=[])
    restarted, _ = ready(tmp_path)
    reconcile_capture_task(restarted, restarted.tasks.get_task(parts[0].id))
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'needs_review'
    for task in restarted.tasks.list_tasks(status='blocked'):
        restarted.tasks.update_task(task.id, status='pending', phase=task._prev_phase,
                                    attempt_count=0, blockers=[])
    restarted, _ = ready(tmp_path)
    reconcile_capture_task(restarted, restarted.tasks.get_task(parts[0].id))
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'queued'
    assert metadata(tmp_path) == before
    assert len(restarted.tasks.list_tasks()) == len(parts)


@pytest.mark.parametrize('previous', ['blocked', 'complete', 'invalid'])
def test_invalid_resume_phase_is_not_approved(tmp_path, previous):
    brain, client, capture, parts = blocked_capture(tmp_path)
    brain.tasks.update_task(parts[0].id, _prev_phase=previous)
    assert client.post(f'/api/ui/approvals/{parts[0].id}/approve').status_code == 400
    assert brain.tasks.get_task(parts[0].id).status == 'blocked'
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'needs_review'


def test_approval_replay_never_resets_attempts_or_global_budget(tmp_path):
    from drift.providers import CallBudget
    brain, client, _, parts = blocked_capture(tmp_path)
    CallBudget(str(tmp_path)).reserve()
    assert client.post(f'/api/ui/approvals/{parts[0].id}/approve').status_code == 200
    brain.tasks.update_task(parts[0].id, attempt_count=1)
    assert client.post(f'/api/ui/approvals/{parts[0].id}/approve').status_code == 200
    assert brain.tasks.get_task(parts[0].id).attempt_count == 1
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 1


def test_approval_preserves_completed_sibling_and_partial_outcome(tmp_path):
    from copy import deepcopy
    from drift.outcomes import record_answer
    brain, client, capture, parts = blocked_capture(tmp_path, 'Thought part. ' * 100)
    first, remaining = parts
    assert client.post(f'/api/ui/approvals/{first.id}/approve').status_code == 200
    record_answer(brain, first, '{"summary": "Retained partial answer"}', 'answers/partial.md')
    brain._complete_report_task(first, 'answers/partial.md')
    outcome = deepcopy(brain.ledger.data['ideas'][0]['outcomes'])
    before = metadata(tmp_path)
    assert client.post(f'/api/ui/approvals/{remaining.id}/approve').status_code == 200
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'queued'
    assert brain.tasks.get_task(first.id).status == 'complete'
    assert brain.ledger.data['ideas'][0]['outcomes'] == outcome
    assert metadata(tmp_path) == before
