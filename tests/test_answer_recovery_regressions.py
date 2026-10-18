"""Retained answers survive interruption at every finalization checkpoint."""
import asyncio
import json
from pathlib import Path

import pytest

from drift.brain import Brain
from drift.capture_store import CaptureStore
from drift.config import config
from drift.intake import stage_captures
from drift.memory import MemoryStream
from drift.task import PHASES


def ready(root):
    brain = Brain({'name': 'answer-recovery'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


@pytest.mark.parametrize('checkpoint', ['rename', 'memory', 'outcome_before', 'outcome_after',
                                      *PHASES[1:-1], 'capture'])
@pytest.mark.parametrize('budget', [0, 200])
def test_restart_replays_finalization_without_model_or_answer_replacement(tmp_path, monkeypatch, checkpoint, budget):
    monkeypatch.setitem(config, 'embeddings_enabled', False)
    monkeypatch.setitem(config, 'llm_scoring_enabled', False)
    brain = ready(tmp_path)
    capture = CaptureStore(str(tmp_path)).capture('Synthetic thought, preserved exactly')['capture']
    stage_captures(brain)
    task = brain.tasks.get_next_task()
    text = json.dumps({'summary': 'FIRST retained answer', 'qualification': 'PARKED',
                       'findings': ['a complete retained finding']})
    import drift.outcomes as outcomes
    import drift.brain as module

    def fail(*args, **kwargs):
        raise OSError('injected finalization interruption')

    with monkeypatch.context() as patch:
        if checkpoint == 'rename':
            replace = module.os.replace
            def interrupt_replace(source, target):
                if str(target).endswith(task.id + '.md'):
                    fail()
                return replace(source, target)
            patch.setattr(module.os, 'replace', interrupt_replace)
        elif checkpoint == 'memory':
            patch.setattr(brain.stream, 'add', fail)
        elif checkpoint.startswith('outcome_'):
            record = outcomes.record_answer
            def interrupt_outcome(*args):
                if checkpoint == 'outcome_after':
                    record(*args)
                fail()
            patch.setattr(outcomes, 'record_answer', interrupt_outcome)
        elif checkpoint == 'capture':
            patch.setattr(outcomes, 'finish_capture_task', fail)
        else:
            update = brain.tasks.update_task
            def interrupt_update(task_id, **changes):
                if changes.get('phase') == checkpoint:
                    fail()
                return update(task_id, **changes)
            patch.setattr(brain.tasks, 'update_task', interrupt_update)
        with pytest.raises(OSError, match='injected'):
            asyncio.run(brain._finish_answer(task, text))

    answer = tmp_path / 'answers' / (task.id + '.md')
    retained = answer if answer.exists() else Path(str(answer) + '.tmp')
    artifact = retained.read_bytes()
    restarted = ready(tmp_path)
    calls = []
    def unexpected_model(*args, **kwargs):
        calls.append(1)
        return {'text': 'WRONG replacement', 'tool_calls': [], 'output': []}
    monkeypatch.setattr(module, 'chat', unexpected_model)
    monkeypatch.setattr(restarted, '_create_attention_task', lambda: None)
    monkeypatch.setitem(config, 'weekly_max_model_calls', budget)
    asyncio.run(restarted._think_once())
    assert calls == []
    assert restarted.tasks.get_task(task.id).status == 'complete'
    assert answer.read_bytes() == artifact
    saved = CaptureStore(str(tmp_path)).get(capture['id'])
    assert saved['status'] == 'processed'
    assert saved['text'] == capture['text']
    idea = next(i for i in restarted.ledger.data['ideas'] if i['id'] == task.idea_id)
    assert idea['outcomes'][task.id]['summary'] == 'FIRST retained answer'
    assert idea['status'] == 'PARKED'
    assert len([e for e in restarted.ledger.data['events'] if e['source'] == 'outcome:' + task.id]) == 1


def test_legacy_committed_answer_recovers_before_first_task_marker(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    capture = CaptureStore(str(tmp_path)).capture('Synthetic pre-upgrade thought')['capture']
    stage_captures(brain)
    task = brain.tasks.get_next_task()
    answer = tmp_path / 'answers' / (task.id + '.md')
    answer.parent.mkdir()
    text = '{"summary": "Legacy retained answer", "qualification": "PARKED"}'
    artifact = f'# {task.goal}\n\nStatus: unverified advisory answer; owner review required.\n\n{text}\n'
    answer.write_text(artifact, encoding='utf-8')
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    asyncio.run(brain._think_once())
    assert task.status == 'complete'
    assert answer.read_text(encoding='utf-8') == artifact
    assert CaptureStore(str(tmp_path)).get(capture['id'])['status'] == 'processed'


def test_full_answer_is_replayed_without_truncating_structured_outcome(tmp_path, monkeypatch):
    brain = ready(tmp_path)
    task = brain.tasks.create_task('Review synthetic text', 'Retain complete answer')
    text = json.dumps({'padding': 'x' * 13000, 'summary': 'Complete tail', 'qualification': 'PARKED'})
    import drift.outcomes as outcomes
    with monkeypatch.context() as patch:
        def fail(*args):
            raise OSError('outcome interrupted')
        patch.setattr(outcomes, 'record_answer', fail)
        with pytest.raises(OSError):
            asyncio.run(brain._finish_answer(task, text))
    answer = tmp_path / 'answers' / (task.id + '.md')
    assert text in answer.read_text(encoding='utf-8')
    restarted = ready(tmp_path)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    asyncio.run(restarted._think_once())
    assert restarted.tasks.get_task(task.id).status == 'complete'
    events = [e for e in restarted.ledger.data['events'] if e['source'] == 'outcome:' + task.id]
    assert events[0]['summary'] == 'Complete tail'


@pytest.mark.parametrize('artifact', ['truncated-temporary', 'unrelated-final'])
def test_unfinished_or_unrelated_artifacts_are_not_promoted_to_answers(tmp_path, monkeypatch, artifact):
    brain = ready(tmp_path)
    task = brain.tasks.create_task('Review synthetic text', 'Retain complete answer')
    answer = tmp_path / 'answers' / (task.id + '.md')
    answer.parent.mkdir()
    if artifact == 'truncated-temporary':
        Path(str(answer) + '.tmp').write_text(
            f'# {task.goal}\n\nStatus: unverified advisory answer; owner review required.\n\nUnfinished',
            encoding='utf-8')
    else:
        answer.write_text('# Unrelated file, not a retained answer\n', encoding='utf-8')
    calls = []
    def model(*args, **kwargs):
        calls.append(1)
        return {'text': 'A fresh completed answer', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', model)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 200)
    asyncio.run(brain._think_once())
    assert calls == [1]
    assert task.status == 'complete'
    assert 'A fresh completed answer' in answer.read_text(encoding='utf-8')


@pytest.mark.parametrize('checkpoint', ['rename', 'memory', 'connect'])
def test_service_loop_keeps_retained_answer_resumable_after_failure(tmp_path, monkeypatch, checkpoint):
    from drift.task import TaskStore
    brain = ready(tmp_path)
    capture = CaptureStore(tmp_path).capture('Synthetic service-loop thought')['capture']
    stage_captures(brain)
    task_id = brain.tasks.get_next_task().id
    update = TaskStore.update_task
    import drift.brain as module
    async def stop_loop():
        brain.stop()
    monkeypatch.setitem(config, 'shell_enabled', False)
    monkeypatch.setitem(config, 'thinking_pace_seconds', 0)
    monkeypatch.setattr(brain, '_idle_wander', stop_loop)
    monkeypatch.setattr(brain, 'should_plan', lambda: False)
    monkeypatch.setattr(MemoryStream, 'should_reflect', lambda self: False)
    monkeypatch.setattr(module, 'chat', lambda *a, **k: {
        'text': 'FIRST retained answer from service', 'tool_calls': [], 'output': []})
    with monkeypatch.context() as fault:
        if checkpoint == 'connect':
            def interrupt(store, task_id, **changes):
                if changes.get('phase') == 'connect':
                    raise OSError('synthetic finalization interruption')
                return update(store, task_id, **changes)
            fault.setattr(TaskStore, 'update_task', interrupt)
        elif checkpoint == 'memory':
            fault.setattr(MemoryStream, 'add', lambda *a, **k: (_ for _ in ()).throw(OSError('synthetic memory failure')))
        else:
            replace = module.os.replace
            def interrupt(source, target):
                if str(target).endswith(task_id + '.md'):
                    raise OSError('synthetic rename failure')
                return replace(source, target)
            fault.setattr(module.os, 'replace', interrupt)
        asyncio.run(brain.run())
    restarted = ready(tmp_path)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 0)
    monkeypatch.setattr(module, 'chat', lambda *a, **k: (_ for _ in ()).throw(AssertionError('No replacement call')))
    asyncio.run(restarted._think_once())
    assert restarted.tasks.get_task(task_id).status == 'complete'
    assert CaptureStore(tmp_path).get(capture['id'])['status'] == 'processed'
    assert 'FIRST retained answer from service' in (tmp_path / 'answers' / (task_id + '.md')).read_text(encoding='utf-8')
