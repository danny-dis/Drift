"""Explicit approval must cover the reviewed versions, not later archives."""
from drift.intake import stage_captures
from drift.providers import CallBudget
from drift.task import TaskStore
from tests.test_capture_ux import ready


def test_older_approval_cannot_cross_another_archive_restore(tmp_path, monkeypatch):
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Approval boundary source'}).json()['capture']
    stage_captures(brain)
    task = brain.tasks.list_tasks()[0]
    path = '/api/ui/captures/' + capture['id']
    assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert client.post(path+'/restore', json={'confirm': True}).status_code == 200
    update = brain.tasks.update_task
    def crossed(*args, **kwargs):
        if kwargs.get('processing_approved') and kwargs.get('status') == 'pending':
            revision = client.get(path).json()['capture']['revision']
            assert client.request('DELETE', path, json={'confirm': True, 'expected_revision': revision}).status_code == 200
            assert client.post(path+'/restore', json={'confirm': True}).status_code == 200
        return update(*args, **kwargs)
    monkeypatch.setattr(brain.tasks, 'update_task', crossed)
    assert client.post('/api/ui/approvals/'+task.id+'/approve').status_code == 409
    assert TaskStore(str(tmp_path)).get_next_task() is None
    assert task.archive_hold and task.status == 'blocked'
    monkeypatch.setattr(brain.tasks, 'update_task', update)
    assert client.post('/api/ui/approvals/'+task.id+'/approve').status_code == 200
    assert TaskStore(str(tmp_path)).get_next_task().id == task.id
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0
