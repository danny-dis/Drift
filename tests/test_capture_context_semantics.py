"""Capture context must keep the owner's subject separate from processing policy."""
import json

from drift.brain import Brain
from drift.memory import MemoryStream
from drift.task import Task
from drift.config import config
import pytest


def ready(root):
    brain = Brain({'name': 'capture-test'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


def test_capture_subject_is_not_processing_policy_or_unrelated_history(tmp_path):
    brain = ready(tmp_path)
    brain.ledger.data['events'].append({'summary': 'UNRELATED_EVENT: rotate credentials'})
    brain.stream.memories.append({'id': 'memory_0', 'content': 'UNRELATED_MEMORY: follow the password privacy instructions',
                                  'importance': 10, 'timestamp': '', 'kind': 'thought'})
    brain._current_focus = 'UNRELATED_FOCUS: configure authentication'
    task = Task('test', 'PROCESS_GOAL: organize inbox', 'PROCESS_OBJECTIVE: keep local',
                source_text='A coffee cart near the railway station with reusable cups.')

    instructions, inputs, meta = brain._build_task_context(task)

    assert len(inputs) == 1
    assert json.loads(inputs[0]['content']) == {'original_thought_part': task.source_text}
    assert 'Summarize only the current original_thought_part' in instructions
    assert 'not process instructions' in instructions
    assert 'not unrelated memories' in instructions
    assert 'credentials' in instructions
    assert 'untrusted' in instructions
    assert 'qualification' in instructions
    assert meta['selected_memory_ids'] == []
    assert meta['selection_scores'] == {}
    assert meta['evidence_ids'] == []


@pytest.mark.parametrize('context_budget', [250, 7000])
def test_long_escaped_source_is_bounded_without_cutting_json(tmp_path, monkeypatch, context_budget):
    monkeypatch.setitem(config, 'context_max_chars', context_budget)
    monkeypatch.setitem(config, 'max_context_chars', 4500)
    brain = ready(tmp_path)
    original = ('Coffee cart \"cups\"\n\\ café ' * 1000)
    task = Task('long', 'PROCESS_GOAL', 'PROCESS_OBJECTIVE', source_text=original)
    instructions, inputs, meta = brain._build_task_context(task)
    encoded = json.dumps(inputs, ensure_ascii=False)
    assert len(encoded) <= context_budget
    assert len(instructions) + len(encoded) <= 4500
    assert len(instructions) <= 4500 // 3
    part = json.loads(inputs[0]['content'])['original_thought_part']
    assert part and original.startswith(part)
    assert task.source_text == original
    assert meta['source_truncated'] is True
    assert meta['estimated_tokens'] == max(1, (len(instructions) + len(encoded)) // 4)
