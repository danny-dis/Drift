import asyncio
import json
from pathlib import Path

from drift.brain import Brain
from drift.memory import MemoryStream


def ready(root):
    brain = Brain({'name': 'private'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


def test_model_bound_credentials_are_redacted_without_altering_task_original(tmp_path, monkeypatch):
    import drift.brain as module
    brain = ready(tmp_path)
    original = 'password=synthetic-secret-for-test and Bearer synthetic-test-token'
    task = brain.tasks.create_task('Question', original)
    sent = []
    def model(input_list, *args, **kwargs):
        sent.append(json.dumps(input_list))
        return {'text': 'Retained safe answer', 'output': [], 'tool_calls': []}
    monkeypatch.setattr(module, 'chat', model)
    asyncio.run(brain._invoke_model(task, [{'role': 'user', 'content': original}], 'rules'))
    assert 'synthetic-secret-for-test' not in sent[0]
    assert 'synthetic-test-token' not in sent[0]
    assert brain.tasks.get_task(task.id).objective == original


def test_diagnostics_do_not_copy_private_inputs_into_shared_log(tmp_path, monkeypatch):
    import drift.brain as module
    shared = tmp_path / 'shared.jsonl'
    monkeypatch.setattr(module, 'LOG_PATH', str(shared))
    brain = ready(tmp_path / 'box')
    asyncio.run(brain._emit_api_call('rules', [{'role': 'user', 'content': 'private thought marker'}],
                                   {'output': [], 'text': 'answer', 'model': 'fixture'}))
    assert not shared.exists()
    journal = Path(brain.env_path) / 'runtime_calls.jsonl'
    assert journal.exists()
    assert 'private thought marker' not in journal.read_text(encoding='utf-8')


def test_transient_api_history_is_bounded(tmp_path):
    brain = ready(tmp_path)
    async def calls():
        for _ in range(125):
            await brain._emit_api_call('rules', [], {'output': []})
    asyncio.run(calls())
    assert len(brain.api_calls) <= 100
