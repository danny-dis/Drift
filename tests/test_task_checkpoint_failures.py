from unittest.mock import patch

import pytest

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.intake import stage_captures
from drift.memory import MemoryStream
from drift.task import TaskStore


def ready_brain(root):
    brain = Brain({'name': 'recovery'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


def test_failed_creation_does_not_publish_a_ghost_task(tmp_path):
    store = TaskStore(str(tmp_path))
    with patch('drift.task.os.replace', side_effect=OSError('checkpoint failed')):
        with pytest.raises(OSError):
            store.create_task('retain original', 'checkpoint safely')
    assert store.list_tasks() == []
    assert TaskStore(str(tmp_path)).list_tasks() == []
    created = store.create_task('retry', 'checkpoint safely')
    assert created.id == 'task-000000'


def test_failed_completion_keeps_existing_reference_and_disk_pending(tmp_path):
    store = TaskStore(str(tmp_path))
    task = store.create_task('retain original', 'checkpoint safely')
    original = task.to_dict()
    with patch('drift.task.os.replace', side_effect=OSError('checkpoint failed')):
        with pytest.raises(OSError):
            store.update_task(task.id, status='complete', last_evidence='report.md')
    assert task.to_dict() == original
    assert store.get_task(task.id).to_dict() == original
    assert TaskStore(str(tmp_path)).get_task(task.id).to_dict() == original
    updated = store.update_task(task.id, status='complete', last_evidence='report.md')
    assert updated is task
    assert task.status == 'complete'


def test_invalid_partial_update_does_not_leak_prior_field_mutation(tmp_path):
    store = TaskStore(str(tmp_path))
    task = store.create_task('retain original', 'checkpoint safely')
    before = task.to_dict()
    with pytest.raises(AttributeError):
        store.update_task(task.id, status='complete', unknown_field=True)
    assert task.to_dict() == before


def test_intake_after_failed_creation_recovers_a_persisted_task(tmp_path):
    brain = ready_brain(tmp_path)
    capture = CaptureStore(tmp_path).capture('An interrupted original', 'retry')['capture']
    with patch('drift.task.os.replace', side_effect=OSError('checkpoint failed')):
        with pytest.raises(OSError):
            stage_captures(brain)
    stage_captures(brain)
    reopened = TaskStore(str(tmp_path))
    stored = CaptureStore(tmp_path).get(capture['id'])
    assert reopened.get_task(stored['task_id']) is not None
    assert stored['status'] == 'queued'


def test_intake_cannot_mark_failed_completion_processed(tmp_path):
    brain = ready_brain(tmp_path)
    capture = CaptureStore(tmp_path).capture('An interrupted original', 'retry')['capture']
    stage_captures(brain)
    task = brain.tasks.list_tasks()[0]
    with patch('drift.task.os.replace', side_effect=OSError('checkpoint failed')):
        with pytest.raises(OSError):
            brain.tasks.update_task(task.id, status='complete')
    stage_captures(brain)
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'queued'
    assert TaskStore(str(tmp_path)).get_task(task.id).status == 'pending'
