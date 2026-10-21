"""Wiki queue eligibility and interrupted handoff must never strand pending work."""
import pytest
from drift.organism import Project
from drift.providers import CallBudget
from tests.test_capture_ux import ready


def test_global_wiki_rejects_sources_held_by_an_archived_project(tmp_path):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Archived source project', ''))
    brain.ledger.add_idea('Related idea is not separately archived')
    brain.ledger.mutate(lambda data: data['ideas'][0].update(related_projects=['one']))
    assert client.request('DELETE', '/api/ui/projects/one', json={'confirm': True, 'expected_revision': 0}).status_code == 200
    response = client.post('/api/ui/wiki/generate', json={'title': 'Global', 'confirm': True})
    assert response.status_code == 422
    assert client.get('/api/ui/wiki').json()['pages'] == []
    assert brain.tasks.list_tasks() == []


def test_interrupted_queue_without_task_becomes_actionable_block_not_permanent_queue(tmp_path, monkeypatch):
    from drift.wiki import queue_wiki
    brain, _ = ready(tmp_path)
    brain.ledger.add_idea('Source remains available after an interrupted queue')
    def crash(*args, **kwargs):
        raise KeyboardInterrupt('simulated process loss before task persistence')
    with monkeypatch.context() as scoped:
        scoped.setattr(brain.tasks, 'create_task', crash)
        with pytest.raises(KeyboardInterrupt):
            queue_wiki(brain, 'Interrupted queue', None)
    restarted, client = ready(tmp_path)
    pages = client.get('/api/ui/wiki').json()['pages']
    assert len(pages) == 1
    page = client.get('/api/ui/wiki/' + pages[0]['id']).json()['page']
    assert page['status'] == 'blocked' and page['task_id'] is None
    assert page['sources'] and page['text'] == ''
    assert 'interrupted' in ' '.join(page['errors']).lower()
    assert not restarted.tasks.list_tasks()
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0
    assert client.get('/api/ui/wiki/' + page['id']).json()['page']['revision'] == page['revision']


def test_interrupted_queue_links_existing_task_instead_of_creating_duplicate(tmp_path, monkeypatch):
    import drift.wiki as wiki
    brain, _ = ready(tmp_path)
    brain.ledger.add_idea('Source for recoverable task handoff')
    update = wiki._update_page
    def crash(brain, page_id, **changes):
        if 'task_id' in changes:
            raise KeyboardInterrupt('simulated loss after durable task creation')
        return update(brain, page_id, **changes)
    with monkeypatch.context() as scoped:
        scoped.setattr(wiki, '_update_page', crash)
        with pytest.raises(KeyboardInterrupt):
            wiki.queue_wiki(brain, 'Recover task handoff', None)
    tasks = brain.tasks.list_tasks()
    assert len(tasks) == 1
    restarted, client = ready(tmp_path)
    pages = client.get('/api/ui/wiki').json()['pages']
    assert len(pages) == 1 and pages[0]['task_id'] == tasks[0].id
    assert pages[0]['status'] == 'queued'
    assert len(restarted.tasks.list_tasks()) == 1
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0


def test_recovered_orphan_task_reports_exhausted_daily_allowance(tmp_path, monkeypatch):
    import drift.wiki as wiki
    from drift.config import config
    brain, _ = ready(tmp_path)
    brain.ledger.add_idea('Source for interrupted zero-allowance request')
    monkeypatch.setitem(config, 'daily_max_model_calls', 0)
    update = wiki._update_page
    def crash(brain, page_id, **changes):
        if 'task_id' in changes:
            raise KeyboardInterrupt('loss before allowance check')
        return update(brain, page_id, **changes)
    with monkeypatch.context() as scoped:
        scoped.setattr(wiki, '_update_page', crash)
        with pytest.raises(KeyboardInterrupt):
            wiki.queue_wiki(brain, 'Interrupted allowance check', None)
    restarted, client = ready(tmp_path)
    page = client.get('/api/ui/wiki').json()['pages'][0]
    assert page['status'] == 'blocked'
    assert restarted.tasks.get_task(page['task_id']).status == 'blocked'
    assert 'allowance' in ' '.join(page['errors']).lower()
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0


def test_archive_restore_during_queue_requires_fresh_permission_for_related_source(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Requested scope', ''))
    brain.ledger.add_project(Project('two', 'Related scope', ''))
    brain.ledger.add_idea('One source linked to both projects')
    brain.ledger.mutate(lambda data: data['ideas'][0].update(related_projects=['one', 'two']))
    create = brain.tasks.create_task
    def crossed_archive(*args, **kwargs):
        assert client.request('DELETE', '/api/ui/projects/two', json={'confirm': True, 'expected_revision': 0}).status_code == 200
        assert client.post('/api/ui/projects/two/restore', json={'confirm': True}).status_code == 200
        return create(*args, **kwargs)
    monkeypatch.setattr(brain.tasks, 'create_task', crossed_archive)
    result = client.post('/api/ui/wiki/generate', json={'title': 'Archive wins over older confirmation', 'project_id': 'one', 'confirm': True})
    assert result.status_code == 200
    queued = result.json()
    assert queued['page']['status'] == 'blocked'
    task = brain.tasks.get_task(queued['task_id'])
    assert task.archive_hold and task.status == 'blocked'
    assert brain.tasks.get_next_task() is None
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0


def test_explicit_new_wiki_can_use_restored_sources_without_resuming_old_work(tmp_path):
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Restored project', ''))
    brain.ledger.add_idea('Visible source for explicitly requested wiki')
    brain.ledger.mutate(lambda data: data['ideas'][0].update(related_projects=['one']))
    assert client.request('DELETE', '/api/ui/projects/one', json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert client.post('/api/ui/projects/one/restore', json={'confirm': True}).status_code == 200
    response = client.post('/api/ui/wiki/generate', json={'title': 'Explicit restored-source wiki', 'project_id': 'one', 'confirm': True})
    assert response.status_code == 200
    queued = response.json()
    assert queued['page']['status'] == 'queued'
    task = brain.tasks.get_task(queued['task_id'])
    assert brain.tasks.get_next_task().id == task.id
    assert task.processing_approved is True
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0
