import asyncio

import pytest

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.intake import stage_captures
from drift.outcomes import block_task


@pytest.mark.parametrize('multipart', [False, True])
def test_restart_repairs_interrupted_approval_before_model_admission(tmp_path, monkeypatch, multipart):
    brain = Brain({'name': 'repair'}, str(tmp_path))
    brain._init_stores()
    store = CaptureStore(tmp_path)
    original = 'Synthetic original ' * (100 if multipart else 1)
    capture = store.capture(original)['capture']
    stage_captures(brain)
    parts = brain.tasks.list_tasks(limit=1000)
    for task in parts:
        block_task(brain, task, 'Review required')
    store.finish(parts[0].id, 'needs_review', 'answers/partial.md', 'Retained partial')
    for task in parts:
        brain.tasks.update_task(task.id, status='pending', phase=task._prev_phase,
                                attempt_count=0, blockers=[])
    restarted = Brain({'name': 'repair'}, str(tmp_path))
    restarted._init_stores()
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    def unexpected_model(*args, **kwargs):
        raise AssertionError('Repair must not call a model')
    monkeypatch.setattr('drift.brain.chat', unexpected_model)
    asyncio.run(restarted._think_once())
    saved = store.get(capture['id'])
    assert saved['status'] == 'queued'
    assert saved['text'] == original
    assert saved['report_path'] == 'answers/partial.md'
    assert len(restarted.tasks.list_tasks()) == len(parts)
