"""Wiki admission holds must retain a phase that explicit approval can resume."""
import copy

import pytest

from drift.config import config
from drift.organism import Project
from drift.providers import CallBudget
from drift.task import TaskStore
from tests.test_capture_ux import ready


def archive_restore(client, project_id):
    path = '/api/ui/projects/' + project_id
    revision = client.get(path).json()['project']['revision']
    removed = client.request('DELETE', path, json={'confirm': True, 'expected_revision': revision})
    assert removed.status_code == 200, removed.text
    restored = client.post(path + '/restore', json={'confirm': True})
    assert restored.status_code == 200, restored.text


@pytest.fixture
def source_box(tmp_path, monkeypatch):
    monkeypatch.setitem(config, 'daily_max_model_calls', 40)
    monkeypatch.setitem(config, 'weekly_max_model_calls', 200)
    def forbidden_provider(*args, **kwargs):
        pytest.fail('Wiki queue, reads and approval must not invoke a provider')
    monkeypatch.setattr('drift.providers._chat_completions', forbidden_provider)
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Requested project', ''))
    brain.ledger.add_project(Project('two', 'Related project outside requested scope', ''))
    raw = '  Immutable original wiki evidence\n'
    capture = client.post('/api/ui/captures', json={'text': raw}).json()['capture']
    idea = brain.ledger.add_idea('Editable source projection')
    brain.ledger.mutate(lambda data: data['ideas'][0].update(
        related_projects=['one', 'two'], capture_id=capture['id']))
    return brain, client, capture, idea.id


@pytest.mark.parametrize('archived_project', ['one', 'two'])
def test_queue_archive_restore_preserves_resumable_approval_after_reload(
        tmp_path, monkeypatch, source_box, archived_project):
    brain, client, original, idea_id = source_box
    budget_before = CallBudget(str(tmp_path)).status()
    create = brain.tasks.create_task
    confirmation = {}
    saved_page = {}

    def cross_creation(*args, **kwargs):
        page_id = kwargs['wiki_page_id']
        brain.ledger.reload()
        page = next(p for p in brain.ledger.data['wiki_pages'] if p['id'] == page_id)
        assert page['task_id'] is None
        assert page_id in brain._wiki_queueing
        assert client.get('/api/ui/wiki/' + page_id).json()['page']['status'] == 'queued'
        assert brain.tasks.list_tasks() == []
        saved_page.update(copy.deepcopy(page))
        confirmation.update(kwargs['processing_approval'])
        assert confirmation['project:' + archived_project] == 0
        archive_restore(client, archived_project)
        task = create(*args, **kwargs)
        assert task.archive_hold and task.phase == task.status == 'blocked'
        assert task._prev_phase == 'capture'
        durable = TaskStore(str(tmp_path)).get_task(task.id)
        assert durable.processing_approval == confirmation
        assert durable._prev_phase == 'capture'
        return task

    with monkeypatch.context() as scoped:
        scoped.setattr(brain.tasks, 'create_task', cross_creation)
        response = client.post('/api/ui/wiki/generate', json={
            'title': 'Recover explicit wiki permission', 'project_id': 'one', 'confirm': True})
    assert response.status_code == 200, response.text
    queued = response.json()
    assert queued['page']['status'] == 'blocked'
    assert queued['page']['task_id'] == queued['task_id']
    assert not brain._wiki_queueing
    restarted, other = ready(tmp_path)
    task = restarted.tasks.get_task(queued['task_id'])
    assert task.archive_hold and task.phase == task.status == 'blocked'
    assert task.processing_approval == confirmation
    assert TaskStore(str(tmp_path)).get_next_task() is None
    update = restarted.tasks.update_task
    raced = []

    def cross_approval(*args, **kwargs):
        if kwargs.get('processing_approved') and kwargs.get('status') == 'pending':
            raced.append(dict(kwargs['processing_approval']))
            archive_restore(other, archived_project)
        return update(*args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(restarted.tasks, 'update_task', cross_approval)
        stale = other.post('/api/ui/approvals/' + task.id + '/approve')
    assert stale.status_code == 409, (stale.text, task._prev_phase)
    assert len(raced) == 1
    assert raced[0]['project:' + archived_project] == 2
    durable = TaskStore(str(tmp_path))
    assert durable.get_next_task() is None
    assert durable.get_task(task.id)._prev_phase == 'capture'
    assert durable.get_task(task.id).processing_approval == confirmation

    fresh_brain, fresh_client = ready(tmp_path)
    fresh = fresh_client.post('/api/ui/approvals/' + task.id + '/approve')
    assert fresh.status_code == 200, fresh.text
    approved_store = TaskStore(str(tmp_path))
    approved = approved_store.get_task(task.id)
    assert approved.phase == 'capture'
    assert approved.status == 'pending' and not approved.archive_hold
    assert approved.processing_approval['project:' + archived_project] == 4
    assert approved_store.get_next_task().id == task.id
    assert len(approved_store.list_tasks()) == 1
    assert fresh_client.get('/api/ui/captures/' + original['id']).json()['capture'] == original
    fresh_brain.ledger.reload()
    page = next(p for p in fresh_brain.ledger.data['wiki_pages'] if p['id'] == queued['page']['id'])
    for field in ('sources', '_snapshots', '_source_catalog'):
        assert page[field] == saved_page[field]
    assert {s['id'] for s in page['sources']} == {'one', idea_id, original['id']}
    source = next(p for p in fresh_brain.ledger.data['projects'] if p['id'] == archived_project)
    assert source['processing_hold'] and not source['archived']
    assert fresh_brain.receipts.get_receipts_for_task(task.id) == []
    assert CallBudget(str(tmp_path)).status() == budget_before


def test_budget_admission_preserves_phase_when_archive_wins_after_source_check(
        tmp_path, monkeypatch, source_box):
    brain, client, original, _ = source_box
    budget_before = CallBudget(str(tmp_path)).status()
    checked = []

    def archive_before_budget_result(budget):
        task, = brain.tasks.list_tasks()
        assert task.phase == 'capture' and task.status == 'pending'
        archive_restore(client, 'one')
        assert task.phase == task.status == 'blocked'
        assert task._prev_phase == 'capture' and task.archive_hold
        checked.append(task.id)
        return False

    with monkeypatch.context() as scoped:
        scoped.setattr(CallBudget, 'can_call', archive_before_budget_result)
        response = client.post('/api/ui/wiki/generate', json={
            'title': 'Archive during budget admission', 'project_id': 'one', 'confirm': True})
    assert response.status_code == 200, response.text
    queued = response.json()
    assert checked == [queued['task_id']]
    assert queued['page']['status'] == 'blocked'
    assert 'allowance' in ' '.join(queued['page']['errors']).lower()
    assert not brain._wiki_queueing
    durable = TaskStore(str(tmp_path))
    task = durable.get_task(queued['task_id'])
    assert task.archive_hold and task.phase == task.status == 'blocked'
    assert task._prev_phase == 'capture'
    assert durable.get_next_task() is None
    restarted, other = ready(tmp_path)
    approved = other.post('/api/ui/approvals/' + task.id + '/approve')
    assert approved.status_code == 200, approved.text
    assert TaskStore(str(tmp_path)).get_next_task().id == task.id
    assert len(restarted.tasks.list_tasks()) == 1
    assert other.get('/api/ui/captures/' + original['id']).json()['capture'] == original
    assert restarted.receipts.get_receipts_for_task(task.id) == []
    assert CallBudget(str(tmp_path)).status() == budget_before


def test_orphan_budget_recovery_preserves_phase_when_archive_wins_during_read(
        tmp_path, monkeypatch, source_box):
    import drift.wiki as wiki
    brain, _, original, _ = source_box
    create = brain.tasks.create_task

    def lose_process_after_save(*args, **kwargs):
        create(*args, **kwargs)
        raise KeyboardInterrupt('synthetic process loss before source and budget admission')

    with monkeypatch.context() as scoped:
        scoped.setattr(brain.tasks, 'create_task', lose_process_after_save)
        with pytest.raises(KeyboardInterrupt):
            wiki.queue_wiki(brain, 'Recover interrupted budget admission', 'one')
    assert not brain._wiki_queueing
    restarted, client = ready(tmp_path)
    task, = restarted.tasks.list_tasks()
    restarted.ledger.reload()
    saved_page, = restarted.ledger.data['wiki_pages']
    saved_page = copy.deepcopy(saved_page)
    assert saved_page['task_id'] is None
    assert task.phase == 'capture' and task.status == 'pending'
    budget_before = CallBudget(str(tmp_path)).status()
    checked = []

    def archive_before_budget_result(budget):
        archive_restore(client, 'one')
        assert task.phase == task.status == 'blocked'
        assert task._prev_phase == 'capture'
        checked.append(task.id)
        return False

    with monkeypatch.context() as scoped:
        scoped.setattr(CallBudget, 'can_call', archive_before_budget_result)
        recovered = client.get('/api/ui/wiki/' + saved_page['id'])
    assert recovered.status_code == 200, recovered.text
    page = recovered.json()['page']
    assert checked == [task.id]
    assert page['task_id'] == task.id and page['status'] == 'blocked'
    assert 'allowance' in ' '.join(page['errors']).lower()
    durable = TaskStore(str(tmp_path))
    assert durable.get_task(task.id)._prev_phase == 'capture'
    assert durable.get_task(task.id).archive_hold
    assert durable.get_next_task() is None
    # Repeated reads reconcile only the existing durable task, never replacement work.
    # The first read's source check precedes the archive race; the next read
    # legitimately checkpoints staleness before subsequent reads become stable.
    reread = client.get('/api/ui/wiki/' + saved_page['id']).json()['page']
    assert reread['stale'] and reread['task_id'] == task.id
    assert client.get('/api/ui/wiki/' + saved_page['id']).json()['page']['revision'] == reread['revision']
    assert len(TaskStore(str(tmp_path)).list_tasks()) == 1
    after_reload, other = ready(tmp_path)
    approved = other.post('/api/ui/approvals/' + task.id + '/approve')
    assert approved.status_code == 200, approved.text
    assert TaskStore(str(tmp_path)).get_next_task().id == task.id
    after_reload.ledger.reload()
    restored_page, = after_reload.ledger.data['wiki_pages']
    for field in ('sources', '_snapshots', '_source_catalog'):
        assert restored_page[field] == saved_page[field]
    assert other.get('/api/ui/captures/' + original['id']).json()['capture'] == original
    assert after_reload.receipts.get_receipts_for_task(task.id) == []
    assert CallBudget(str(tmp_path)).status() == budget_before
