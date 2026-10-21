"""Offline regressions for implicit, project-selected context source lineage."""
import asyncio
import json

import pytest

from drift.archive_policy import ArchivePolicy
from drift.organism import Project
from tests.test_capture_ux import ready


def project_task(root):
    brain, client = ready(root)
    brain.ledger.add_project(Project('one', 'Active project', ''))
    idea = brain.ledger.add_idea('ARCHIVED_PRIVATE_SOURCE_SENTINEL')
    brain.ledger.mutate(lambda d: d['ideas'][0].update(related_projects=['one']))
    task = brain.tasks.create_task('Review project', 'Understand project', project_id='one')
    return brain, client, idea, task


def archive_idea(client, idea):
    response = client.request('DELETE', '/api/ui/ideas/' + idea.id,
        json={'confirm': True, 'expected_revision': 0})
    assert response.status_code == 200, response.text


def test_project_only_task_omits_archived_related_idea_even_with_stale_ledger(tmp_path):
    brain, client, idea, task = project_task(tmp_path)
    # Keep exactly the stale reader identified in the independent review.
    stale = json.loads(json.dumps(brain.ledger.data))
    archive_idea(client, idea)
    brain.ledger.data = stale
    assert not task.idea_id
    assert not ArchivePolicy(tmp_path).task_suppressed(task)
    assert brain.tasks.get_next_task() is task
    _, inputs, meta = brain._build_task_context(task)
    assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' not in json.dumps(inputs)
    assert idea.id not in meta['evidence_ids']


@pytest.mark.parametrize('boundary', ['before_attempt', 'retry', 'followup', 'result', 'tool_result'])
def test_selected_project_source_archive_stops_execution_boundaries(tmp_path, monkeypatch, boundary):
    import openai
    brain, client, idea, task = project_task(tmp_path)
    original = brain._build_task_context
    calls, emitted, tools = [], [], []

    def build(selected):
        result = original(selected)
        assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' in json.dumps(result[1])
        if boundary == 'before_attempt':
            archive_idea(client, idea)
        return result

    def chat(*args, **kwargs):
        calls.append(1)
        if boundary == 'retry':
            archive_idea(client, idea)
            raise openai.APIConnectionError(request=__import__('httpx').Request('POST', 'https://example.invalid'))
        if boundary == 'result' or boundary == 'followup' and len(calls) == 2:
            archive_idea(client, idea)
        if boundary in ('followup', 'tool_result') and len(calls) == 1:
            return {'text': '', 'output': [], 'tool_calls': [
                {'name': 'read_file', 'arguments': {'path': 'one'}, 'call_id': 'one'}]}
        return {'text': 'DISCARDED_RESPONSE_SENTINEL', 'tool_calls': [], 'output': []}

    def tool(*args, **kwargs):
        tools.append(1)
        if boundary == 'tool_result':
            archive_idea(client, idea)
        return 'DISCARDED_TOOL_SENTINEL'

    async def broadcast(message):
        emitted.append(message)

    monkeypatch.setattr(brain, '_build_task_context', build)
    monkeypatch.setattr('drift.brain.chat', chat)
    monkeypatch.setattr('drift.brain.execute_tool', tool)
    monkeypatch.setattr(brain, '_broadcast', broadcast)
    asyncio.run(brain._think_once())
    assert len(calls) == {'before_attempt': 0, 'retry': 1, 'followup': 2,
        'result': 1, 'tool_result': 1}[boundary]
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(emitted)
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(brain.api_calls)
    assert 'DISCARDED_RESPONSE_SENTINEL' not in json.dumps(brain.stream.get_recent(n=20))
    if boundary == 'tool_result':
        assert 'DISCARDED_TOOL_SENTINEL' not in json.dumps(emitted)
    assert not list((tmp_path / 'answers').glob('*.md'))
    assert brain.state == 'idle'


@pytest.mark.parametrize('kind', ['event', 'memory', 'memory_chain'])
def test_source_bearing_events_and_memories_do_not_reintroduce_archived_ideas(tmp_path, kind):
    from drift.organism import DriftEvent
    brain, client, idea, task = project_task(tmp_path)
    if kind == 'event':
        brain.ledger.add_event(DriftEvent('finding', 'synthetic', 'DERIVED_PRIVATE_SENTINEL',
            related_ideas=[idea.id]))
    else:
        brain.stream.memories = [dict(id='m_0000', content='DERIVED_PRIVATE_SENTINEL',
            timestamp='', importance=5, references=[idea.id])]
        if kind == 'memory_chain':
            brain.stream.memories.append(dict(id='m_0001', content='CHAIN_PRIVATE_SENTINEL',
                timestamp='', importance=5, references=['m_0000']))
    archive_idea(client, idea)
    _, inputs, meta = brain._build_task_context(task)
    assert 'DERIVED_PRIVATE_SENTINEL' not in json.dumps(inputs)
    assert 'CHAIN_PRIVATE_SENTINEL' not in json.dumps(inputs)
    assert not meta['selected_memory_ids']


def test_project_outcome_sources_survive_restart_for_event_and_memory_filtering(tmp_path, monkeypatch):
    from drift.task import TaskStore
    brain, client, idea, task = project_task(tmp_path)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k:
        {'text': 'DERIVED_PRIVATE_SENTINEL', 'tool_calls': [], 'output': []})
    asyncio.run(brain._think_once())
    assert task.status == 'complete'
    assert list((tmp_path / 'answers').glob('*.md'))
    assert any('DERIVED_PRIVATE_SENTINEL' in m['content'] for m in brain.stream.memories)
    archive_idea(client, idea)
    restarted, _ = ready(tmp_path)
    assert TaskStore(str(tmp_path)).get_task(task.id).status == 'complete'
    followup = restarted.tasks.create_task('New project question', 'Review', project_id='one')
    _, inputs, _ = restarted._build_task_context(followup)
    assert 'DERIVED_PRIVATE_SENTINEL' not in json.dumps(inputs)


@pytest.mark.parametrize('kind', ['idea', 'project'])
def test_stale_explicit_original_and_project_facts_are_filtered(tmp_path, kind):
    brain, client, idea, task = project_task(tmp_path)
    task.idea_id = idea.id if kind == 'idea' else ''
    stale = json.loads(json.dumps(brain.ledger.data))
    if kind == 'idea':
        archive_idea(client, idea)
        sentinel = 'ARCHIVED_PRIVATE_SOURCE_SENTINEL'
    else:
        response = client.request('DELETE', '/api/ui/projects/one',
            json={'confirm': True, 'expected_revision': 0})
        assert response.status_code == 200
        sentinel = 'Active project'
    brain.ledger.data = stale
    _, inputs, _ = brain._build_task_context(task)
    assert sentinel not in json.dumps(inputs)


def test_packet_is_revision_bound_even_after_inflight_restore_and_fresh_approval(tmp_path, monkeypatch):
    brain, client, idea, task = project_task(tmp_path)

    def chat(*args, **kwargs):
        archive_idea(client, idea)
        assert client.post('/api/ui/ideas/' + idea.id + '/restore', json={'confirm': True}).status_code == 200
        assert client.post('/api/ui/approvals/' + task.id + '/approve').status_code == 200
        return {'text': 'STALE_PACKET_RESPONSE', 'tool_calls': [], 'output': []}

    monkeypatch.setattr('drift.brain.chat', chat)
    asyncio.run(brain._think_once())
    assert 'STALE_PACKET_RESPONSE' not in json.dumps(brain.api_calls)
    assert 'STALE_PACKET_RESPONSE' not in json.dumps(brain.stream.memories)
    assert not list((tmp_path / 'answers').glob('*.md'))


def test_project_metadata_edit_after_assembly_cannot_send_old_project_facts(tmp_path, monkeypatch):
    brain, client, idea, task = project_task(tmp_path)
    # No sibling idea may incidentally bind project metadata for this test.
    brain.ledger.mutate(lambda d: d['ideas'][0].update(related_projects=[]))
    instructions, inputs, meta = brain._build_task_context(task)
    assert 'Active project' in json.dumps(inputs)
    response = client.patch('/api/ui/projects/one', json={'name': 'New name', 'expected_revision': 0})
    assert response.status_code == 200, response.text
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: pytest.fail('Stale project metadata sent'))
    with pytest.raises(RuntimeError, match='context changed'):
        asyncio.run(brain._invoke_model(task, inputs, instructions, meta))


@pytest.mark.parametrize('lineage', ['projection-only', 'metadata-only', 'canonical-only'])
@pytest.mark.parametrize('restored', [False, True])
def test_original_backed_project_projection_cannot_bypass_archive_or_hold(tmp_path, lineage, restored):
    from contextlib import closing
    import sqlite3
    from drift.intake import stage_captures
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'ORIGINAL_PRIVATE_SENTINEL'}).json()['capture']
    stage_captures(brain)
    iid = 'thought-' + capture['id']
    brain.ledger.add_project(Project('one', 'Visible project', ''))
    brain.ledger.mutate(lambda d: d['ideas'][0].update(related_projects=['one']))
    if lineage in ('metadata-only', 'canonical-only'):
        brain.ledger.mutate(lambda d: d['ideas'][0].pop('capture_id', None))
    if lineage in ('projection-only', 'canonical-only'):
        with closing(sqlite3.connect(tmp_path / 'captures.sqlite3')) as db:
            db.execute('UPDATE captures SET idea_id = NULL WHERE id = ?', (capture['id'],))
            db.commit()
    path = '/api/ui/captures/' + capture['id']
    assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    if restored:
        assert client.post(path + '/restore', json={'confirm': True}).status_code == 200
    task = brain.tasks.create_task('Project-only review', 'Review', project_id='one', processing_approved=True)
    assert not ArchivePolicy(tmp_path).task_suppressed(task)
    _, inputs, meta = brain._build_task_context(task)
    assert 'ORIGINAL_PRIVATE_SENTINEL' not in json.dumps(inputs)
    assert iid not in meta['evidence_ids']
    assert 'idea:' + iid not in task.context_sources


def test_restored_sibling_is_omitted_but_fresh_task_local_approval_can_include_it(tmp_path):
    brain, client, idea, task = project_task(tmp_path)
    archive_idea(client, idea)
    assert client.post('/api/ui/ideas/' + idea.id + '/restore', json={'confirm': True}).status_code == 200
    _, inputs, _ = brain._build_task_context(task)
    assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' not in json.dumps(inputs)
    approved = brain.tasks.create_task('Explicit retry', 'Review', project_id='one',
        idea_id=idea.id, processing_approved=True)
    _, inputs, _ = brain._build_task_context(approved)
    assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' in json.dumps(inputs)
    assert not ArchivePolicy(tmp_path).task_suppressed(approved)
    _, inputs, _ = brain._build_task_context(task)
    assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' not in json.dumps(inputs)


def test_active_scoped_sources_and_unrelated_legacy_memory_remain_available(tmp_path, monkeypatch):
    from drift.organism import DriftEvent
    brain, client, idea, task = project_task(tmp_path)
    brain.ledger.add_project(Project('two', 'Other project', ''))
    unrelated = brain.ledger.add_idea('UNRELATED_IDEA_SENTINEL')
    brain.ledger.mutate(lambda d: d['ideas'][-1].update(related_projects=['two']))
    brain.ledger.add_event(DriftEvent('observation', 'test', 'ACTIVE_EVENT_SENTINEL', related_ideas=[idea.id]))
    brain.stream.memories = [dict(id='m_0000', content='LEGACY_MEMORY_SENTINEL',
        timestamp='', importance=5, references=[])]
    _, inputs, meta = brain._build_task_context(task)
    assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' in json.dumps(inputs)
    assert 'ACTIVE_EVENT_SENTINEL' in json.dumps(inputs)
    assert 'LEGACY_MEMORY_SENTINEL' in json.dumps(inputs)
    assert 'UNRELATED_IDEA_SENTINEL' not in json.dumps(inputs)
    assert unrelated.id not in meta['evidence_ids']
    archive_idea(client, unrelated)
    assert not ArchivePolicy(tmp_path).task_suppressed(task)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k:
        {'text': 'Active answer', 'tool_calls': [], 'output': []})
    asyncio.run(brain._think_once())
    assert task.status == 'complete'


def test_archiving_unselected_sibling_after_render_does_not_block_selected_project(tmp_path, monkeypatch):
    brain, client, omitted, task = project_task(tmp_path)
    for n in range(6):
        brain.ledger.add_idea('Selected safe source ' + str(n))
        brain.ledger.mutate(lambda d: d['ideas'][-1].update(related_projects=['one']))
    instructions, inputs, meta = brain._build_task_context(task)
    assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' not in json.dumps(inputs)
    assert 'idea:' + omitted.id not in task.context_sources
    archive_idea(client, omitted)
    assert not ArchivePolicy(tmp_path).task_suppressed(task)
    calls = []
    def chat(*a, **k):
        calls.append(1)
        return {'text': 'Active answer', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', chat)
    asyncio.run(brain._invoke_model(task, inputs, instructions, meta))
    assert calls == [1]


@pytest.mark.parametrize('kind', ['event', 'memory'])
def test_indirect_sources_remain_guarded_after_assembly(tmp_path, monkeypatch, kind):
    from drift.organism import DriftEvent
    brain, client, idea, task = project_task(tmp_path)
    brain.ledger.mutate(lambda d: d['ideas'][0].update(related_projects=[]))
    if kind == 'event':
        brain.ledger.add_event(DriftEvent('finding', 'test', 'INDIRECT_SENTINEL', related_ideas=[idea.id]))
    else:
        brain.stream.memories = [dict(id='m_0000', content='INDIRECT_SENTINEL',
            timestamp='', importance=5, references=[idea.id])]
    instructions, inputs, meta = brain._build_task_context(task)
    assert 'INDIRECT_SENTINEL' in json.dumps(inputs)
    archive_idea(client, idea)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: pytest.fail('Archived indirect source sent'))
    with pytest.raises(RuntimeError, match='Source archived'):
        asyncio.run(brain._invoke_model(task, inputs, instructions, meta))


def test_legacy_task_without_context_vector_can_still_run(tmp_path, monkeypatch):
    from drift.task import Task
    brain, client = ready(tmp_path)
    legacy = Task.from_dict({'id': 'task-000000', 'goal': 'Old task', 'objective': 'Still works'})
    assert legacy.context_sources == {}
    brain.tasks._tasks[legacy.id] = legacy
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k:
        {'text': 'Legacy answer', 'tool_calls': [], 'output': []})
    asyncio.run(brain._think_once())
    assert legacy.status == 'complete'


def test_worker_scheduling_gap_rechecks_before_physical_attempt(tmp_path, monkeypatch):
    brain, client, idea, task = project_task(tmp_path)
    original = asyncio.to_thread
    calls = []

    async def delayed(function, *args, **kwargs):
        if function.__name__ == 'admitted_chat':
            archive_idea(client, idea)
        return await original(function, *args, **kwargs)

    monkeypatch.setattr('drift.brain.asyncio.to_thread', delayed)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k: calls.append(1))
    asyncio.run(brain._think_once())
    assert calls == []
    assert task.status == 'blocked'


@pytest.mark.parametrize('followup', [False, True])
def test_archived_implicit_context_never_retains_partial_response(tmp_path, monkeypatch, followup):
    brain, client, idea, task = project_task(tmp_path)
    calls = []
    def chat(*args, **kwargs):
        calls.append(1)
        if followup and len(calls) == 1:
            return {'text': '', 'output': [], 'tool_calls': [
                {'name': 'read_file', 'arguments': {'path': 'one'}, 'call_id': 'one'}]}
        archive_idea(client, idea)
        return {'text': 'PRIVATE_PARTIAL_SENTINEL', 'tool_calls': [], 'output': [], 'finish_reason': 'length'}
    monkeypatch.setattr('drift.brain.chat', chat)
    monkeypatch.setattr('drift.brain.execute_tool', lambda *a, **k: 'Safe tool output')
    asyncio.run(brain._think_once())
    assert len(calls) == (2 if followup else 1)
    assert not list((tmp_path / 'answers').glob('*.md'))
    assert 'PRIVATE_PARTIAL_SENTINEL' not in json.dumps(brain.api_calls)
    assert 'PRIVATE_PARTIAL_SENTINEL' not in json.dumps(brain.stream.memories)


def test_archive_at_thought_publication_stops_global_memory_and_outcomes(tmp_path, monkeypatch):
    brain, client, idea, task = project_task(tmp_path)
    original = brain._emit
    async def emit(kind, **data):
        if kind == 'thought':
            archive_idea(client, idea)
        await original(kind, **data)
    monkeypatch.setattr(brain, '_emit', emit)
    monkeypatch.setattr('drift.brain.chat', lambda *a, **k:
        {'text': 'PUBLISH_PRIVATE_SENTINEL', 'tool_calls': [], 'output': []})
    asyncio.run(brain._think_once())
    assert 'PUBLISH_PRIVATE_SENTINEL' not in json.dumps(brain.stream.memories)
    assert not list((tmp_path / 'answers').glob('*.md'))
    assert not brain.ledger.data['projects'][0].get('intelligence')


def test_fresh_approval_rebuilds_previously_archived_project_task_packet(tmp_path, monkeypatch):
    brain, client, idea, task = project_task(tmp_path)
    def removed(*a, **k):
        archive_idea(client, idea)
        return {'text': 'Discarded', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', removed)
    asyncio.run(brain._think_once())
    assert task.archive_hold and task.status == 'blocked'
    assert client.post('/api/ui/ideas/' + idea.id + '/restore', json={'confirm': True}).status_code == 200
    assert client.post('/api/ui/approvals/' + task.id + '/approve').status_code == 200
    assert task.attempt_count == 0  # Existing explicit-retry admission resets the allowance.
    assert brain.tasks.get_next_task() is task
    def fresh(inputs, *a, **k):
        assert 'ARCHIVED_PRIVATE_SOURCE_SENTINEL' in json.dumps(inputs)
        return {'text': 'Fresh response', 'tool_calls': [], 'output': []}
    monkeypatch.setattr('drift.brain.chat', fresh)
    asyncio.run(brain._think_once())
    assert task.status == 'complete'
    assert task.attempt_count == 1
