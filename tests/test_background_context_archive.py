"""Taskless model paths must follow the same source lifecycle as tasks."""
import asyncio
import json

import pytest

from tests.test_project_context_archive import project_task, archive_idea


@pytest.mark.parametrize('method', ['_reflect', '_plan'])
def test_background_omits_archived_memory_and_keeps_active_provenance(tmp_path, monkeypatch, method):
    brain, client, idea, _ = project_task(tmp_path)
    active = brain.ledger.add_idea('ACTIVE_PUBLIC_SOURCE')
    brain.stream.memories = [
        dict(id='m_0000', kind='thought', content='ARCHIVED_BACKGROUND_SENTINEL',
             timestamp='', importance=5, references=[idea.id]),
        dict(id='m_0001', kind='thought', content='ACTIVE_BACKGROUND_SENTINEL',
             timestamp='', importance=5, references=[active.id]),
    ]
    # This generated summary cannot be used as an untracked replacement for
    # lifecycle-filtered project records and memory sources.
    (tmp_path / 'projects.md').write_text('ARCHIVED_BACKGROUND_SENTINEL')
    archive_idea(client, idea)
    calls = []
    async def invoke(task, inputs, instructions, meta=None, **kwargs):
        calls.append((inputs, meta))
        assert 'ARCHIVED_BACKGROUND_SENTINEL' not in json.dumps(inputs)
        assert 'ACTIVE_BACKGROUND_SENTINEL' in json.dumps(inputs)
        assert 'idea:' + active.id in meta['source_revisions']
        return {'text': 'SAFE_BACKGROUND_OUTPUT', 'tool_calls': [], 'output': []}
    monkeypatch.setattr(brain, '_invoke_model', invoke)
    asyncio.run(getattr(brain, method)())
    assert len(calls) == 1
    assert 'ARCHIVED_BACKGROUND_SENTINEL' not in json.dumps(brain.api_calls)
    if method == '_reflect':
        reflections = [m for m in brain.stream.memories if m.get('kind') == 'reflection']
        assert reflections and reflections[-1]['references'] == ['m_0001']
    else:
        assert (tmp_path / 'projects.md').read_text() == 'SAFE_BACKGROUND_OUTPUT'


@pytest.mark.parametrize('boundary', ['before_attempt', 'worker_gap', 'response'])
def test_taskless_invocation_rechecks_source_at_physical_boundaries(tmp_path, monkeypatch, boundary):
    import drift.brain as module
    from types import SimpleNamespace
    brain, client, idea, _ = project_task(tmp_path)
    brain.stream.memories = [dict(id='m_0000', kind='thought', content='BACKGROUND_INPUT',
        timestamp='', importance=5, references=[idea.id])]
    _, _, meta = brain._background_context(10)
    calls = []
    def chat(*args, **kwargs):
        calls.append(1)
        if boundary == 'response':
            archive_idea(client, idea)
        return {'text': 'STALE_BACKGROUND_OUTPUT', 'tool_calls': [], 'output': []}
    monkeypatch.setattr(module, 'chat', chat)
    if boundary == 'before_attempt':
        archive_idea(client, idea)
    elif boundary == 'worker_gap':
        original = asyncio.to_thread
        async def delayed(fn, *args, **kwargs):
            archive_idea(client, idea)
            return await original(fn, *args, **kwargs)
        monkeypatch.setattr(module, 'asyncio', SimpleNamespace(**{**vars(asyncio), 'to_thread': delayed}))
    with pytest.raises(RuntimeError, match='Source archived|context changed'):
        asyncio.run(brain._invoke_model(None, [{'role': 'user', 'content': 'BACKGROUND_INPUT'}],
            'Background', meta, tools=False))
    assert len(calls) == (1 if boundary == 'response' else 0)


@pytest.mark.parametrize('method', ['_reflect', '_plan'])
@pytest.mark.parametrize('boundary', ['before_receipt', 'after_receipt'])
def test_background_publication_rechecks_sources(tmp_path, monkeypatch, method, boundary):
    brain, client, idea, _ = project_task(tmp_path)
    brain.stream.memories = [dict(id='m_0000', kind='thought', content='BACKGROUND_INPUT',
        timestamp='', importance=5, references=[idea.id])]
    (tmp_path / 'projects.md').write_text('KEEP_PREVIOUS_DOCUMENT')
    async def invoke(*args, **kwargs):
        if boundary == 'before_receipt':
            archive_idea(client, idea)
        return {'text': 'STALE_BACKGROUND_OUTPUT', 'tool_calls': [], 'output': []}
    monkeypatch.setattr(brain, '_invoke_model', invoke)
    if boundary == 'after_receipt':
        async def receipt(*args, **kwargs):
            archive_idea(client, idea)
        monkeypatch.setattr(brain, '_emit_api_call', receipt)
    asyncio.run(getattr(brain, method)())
    assert 'STALE_BACKGROUND_OUTPUT' not in json.dumps(brain.api_calls)
    assert not any(m['content'] == 'STALE_BACKGROUND_OUTPUT' for m in brain.stream.memories)
    assert (tmp_path / 'projects.md').read_text() == 'KEEP_PREVIOUS_DOCUMENT'


@pytest.mark.parametrize('restart', [False, True])
def test_generated_focus_never_becomes_untracked_owner_instructions(tmp_path, monkeypatch, restart):
    from tests.test_capture_ux import ready
    brain, client, idea, task = project_task(tmp_path)
    brain.stream.memories = [dict(id='m_0000', kind='thought',
        content='ARCHIVED_PLANNING_FOCUS', timestamp='', importance=5, references=[idea.id])]
    async def plan(*args, **kwargs):
        return {'text': '# Current Focus\nARCHIVED_PLANNING_FOCUS\n',
            'tool_calls': [], 'output': []}
    with monkeypatch.context() as scoped:
        scoped.setattr(brain, '_invoke_model', plan)
        asyncio.run(brain._plan())
    assert brain._current_focus == 'ARCHIVED_PLANNING_FOCUS'
    archive_idea(client, idea)
    if restart:
        brain, _ = ready(tmp_path)
        brain._current_focus = brain._load_current_focus()
        task = brain.tasks.get_task(task.id)
    instructions, inputs, meta = brain._build_task_context(task)
    assert 'ARCHIVED_PLANNING_FOCUS' not in json.dumps(inputs)
    calls = []
    def chat(inputs, tools, instructions, *args, **kwargs):
        calls.append(instructions)
        return {'text': 'Safe response', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', chat)
    asyncio.run(brain._invoke_model(task, inputs, instructions, meta))
    assert calls and 'ARCHIVED_PLANNING_FOCUS' not in calls[0]
    assert (tmp_path / 'projects.md').read_text().endswith('ARCHIVED_PLANNING_FOCUS\n')


def test_reflection_storage_worker_checks_source_after_scheduling_gap(tmp_path, monkeypatch):
    import drift.brain as module
    from types import SimpleNamespace
    from drift.config import config
    brain, client, idea, _ = project_task(tmp_path)
    brain.stream.memories = [dict(id='m_0000', kind='thought', content='SOURCE_INPUT',
        timestamp='', importance=5, references=[idea.id])]
    brain.stream._next_id = 1
    monkeypatch.setitem(config, 'llm_scoring_enabled', False)
    monkeypatch.setitem(config, 'decision_memory_enabled', False)
    monkeypatch.setattr('drift.memory.embed', lambda text: [])
    async def invoke(*args, **kwargs):
        return {'text': 'STALE_BACKGROUND_INSIGHT', 'tool_calls': [], 'output': []}
    monkeypatch.setattr(brain, '_invoke_model', invoke)
    original, crossed = asyncio.to_thread, []
    async def delayed(fn, *args, **kwargs):
        if not crossed:
            archive_idea(client, idea)
            crossed.append(True)
        return await original(fn, *args, **kwargs)
    monkeypatch.setattr(module, 'asyncio', SimpleNamespace(**{**vars(asyncio), 'to_thread': delayed}))
    asyncio.run(brain._reflect())
    assert crossed == [True]
    assert not any(m['content'] == 'STALE_BACKGROUND_INSIGHT' for m in brain.stream.memories)
    assert not (tmp_path / 'memory_stream.jsonl').exists() or 'STALE_BACKGROUND_INSIGHT' not in (tmp_path / 'memory_stream.jsonl').read_text()
