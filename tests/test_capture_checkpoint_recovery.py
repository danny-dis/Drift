import asyncio
import json

import pytest
from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.intake import stage_captures
from drift.memory import MemoryStream


def test_interrupted_final_checkpoint_reopens_without_another_model_call(tmp_path, monkeypatch):
    brain = Brain({'name': 'recovery'}, str(tmp_path))
    brain.stream = MemoryStream(str(tmp_path)); brain._init_stores()
    capture = CaptureStore(str(tmp_path)).capture('A thought to preserve')['capture']
    stage_captures(brain)
    task = brain.tasks.get_next_task()
    update = brain.tasks.update_task
    def interrupt(task_id, **changes):
        if changes.get('phase') == 'complete':
            raise OSError('fixture final-checkpoint interruption')
        return update(task_id, **changes)
    monkeypatch.setattr(brain.tasks, 'update_task', interrupt)
    with pytest.raises(OSError):
        asyncio.run(brain._finish_answer(task, json.dumps({'summary': 'Retained outcome.', 'qualification': 'RESEARCH'})))
    assert CaptureStore(str(tmp_path)).get(capture['id'])['status'] == 'queued'
    restarted = Brain({'name': 'recovery'}, str(tmp_path))
    restarted.stream = MemoryStream(str(tmp_path)); restarted._init_stores()
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    import drift.brain as module
    monkeypatch.setattr(module, 'chat', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No duplicate model call')))
    asyncio.run(restarted._think_once())
    assert restarted.tasks.get_task(task.id).status == 'complete'
    assert CaptureStore(str(tmp_path)).get(capture['id'])['status'] == 'processed'
