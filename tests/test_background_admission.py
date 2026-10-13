import asyncio

import pytest

from drift.brain import Brain
from drift.memory import MemoryStream
from drift.providers import CallBudget


def ready(root):
    brain = Brain({'name': 'background'}, str(root))
    brain.stream = MemoryStream(str(root)); brain._init_stores()
    return brain


def test_failed_planning_waits_for_new_work_instead_of_retrying_every_cycle(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    brain.thought_count = 3
    brain._cycles_since_plan = Brain.PLAN_INTERVAL + 2
    calls = []
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('Injected unavailable provider')
    monkeypatch.setattr('drift.brain.chat', unavailable)
    asyncio.run(brain._plan())
    assert calls == [1]
    assert brain._cycles_since_plan == 0
    brain._cycles_since_plan = Brain.PLAN_INTERVAL + 1
    assert not brain.should_plan()
    brain.thought_count += 1
    assert brain.should_plan()


@pytest.mark.parametrize('phase', ['_plan', '_reflect'])
def test_optional_background_phases_do_not_call_model_when_admission_is_closed(tmp_path, monkeypatch, phase):
    brain = ready(tmp_path)
    brain.stream.add('A remembered synthetic thought', 'thought', 8)
    monkeypatch.setattr(CallBudget, 'can_call', lambda self: False)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No model call permitted')))
    asyncio.run(getattr(brain, phase)())
    assert brain.state != 'planning' and brain.state != 'reflecting'


def test_internal_state_is_not_new_owner_inbox_work(tmp_path):
    brain = ready(tmp_path)
    for name in ['drift_ledger.json', 'tasks.json', 'receipts.jsonl']:
        (tmp_path / name).write_text('{}', encoding='utf-8')
    (tmp_path / 'answers').mkdir(exist_ok=True)
    (tmp_path / 'answers' / 'task-000000.md').write_text('Generated report', encoding='utf-8')
    (tmp_path / 'owner-note.txt').write_text('An actual new owner thought', encoding='utf-8')
    assert brain._scan_env_files() == {'owner-note.txt'}
    assert brain._list_env_files() == ['owner-note.txt']
