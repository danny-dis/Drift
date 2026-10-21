from fastapi.testclient import TestClient
from tests.test_capture_ux import ready
from drift.organism import DriftLedger


def test_idea_project_edit_archive_restore_is_revisioned_and_preserves_metadata(tmp_path):
    brain, client = ready(tmp_path)
    project = client.post('/api/ui/projects', json={'name': 'Example', 'repo': 'owner/repo'}).json()['project']
    idea = client.post('/api/ui/ideas', json={'text': 'Example feature'}).json()['idea']
    def annotate(data):
        data['projects'][0]['intelligence'] = {'summary': 'keep'}
        data['ideas'][0]['custom_note'] = 'keep'
    brain.ledger.mutate(annotate)
    for kind, record, changes in [('projects', project, {'name': 'Renamed'}), ('ideas', idea, {'text': 'Updated idea'})]:
        singular = kind[:-1]
        path = f'/api/ui/{kind}/{record["id"]}'
        result = client.patch(path, json={**changes, 'expected_revision': 0})
        assert result.status_code == 200, result.text
        item = result.json()[singular]
        assert item['revision'] == 1
        assert item.get('custom_note', item.get('intelligence')) in ('keep', {'summary': 'keep'})
        assert client.patch(path, json={**changes, 'expected_revision': 0}).status_code == 409
        assert client.patch(path, json={'untrusted': True, 'expected_revision': 1}).status_code == 422
        removed = client.request('DELETE', path, json={'confirm': True, 'expected_revision': 1})
        assert removed.status_code == 200, removed.text
        assert removed.json()[singular]['archived'] is True
        assert not client.get('/api/ui/' + kind).json()[kind]
        assert len(client.get('/api/ui/' + kind + '?include_archived=true').json()[kind]) == 1
        assert client.get(path).json()[singular]['archived']
        assert client.post(path + '/restore', json={'confirm': True}).status_code == 200
        assert len(client.get('/api/ui/' + kind).json()[kind]) == 1
    persisted = DriftLedger(str(tmp_path))
    assert persisted.data['ideas'][0]['text'] == 'Updated idea'
    assert persisted.data['projects'][0]['name'] == 'Renamed'


def test_project_path_edit_obeys_supervisor_guard(tmp_path):
    from drift.local_runtime import install_project_guard
    brain, _ = ready(tmp_path / 'box')
    from fastapi import FastAPI
    from drift.ui_api import router
    app = FastAPI()
    app.state.drift_brains = {'ux': brain}
    app.include_router(router)
    allowed = tmp_path / 'allowed'
    allowed.mkdir()
    install_project_guard(app, allowed)
    client = TestClient(app)
    project = client.post('/api/ui/projects', json={'name': 'Guarded'}).json()['project']
    path = '/api/ui/projects/' + project['id']
    result = client.patch(path, json={'local_path': str(tmp_path / 'outside'), 'expected_revision': 0})
    assert result.status_code == 403, result.text
    assert client.patch(path, json={'local_path': str(allowed), 'importance': .8, 'expected_revision': 0}).status_code == 200
    assert client.patch(path, json={'importance': 'NaN', 'expected_revision': 1}).status_code == 422


def test_archived_domain_work_stays_suppressed_on_legacy_paths(tmp_path):
    from drift.watcher import GitChange
    brain, client = ready(tmp_path)
    project = client.post('/api/ui/projects', json={'name': 'Example', 'local_path': str(tmp_path)}).json()['project']
    idea = client.post('/api/ui/ideas', json={'text': 'Example feature'}).json()['idea']
    for kind, record in [('ideas', idea), ('projects', project)]:
        response = client.request('DELETE', f'/api/ui/{kind}/{record["id"]}', json={'confirm': True, 'expected_revision': 0})
        assert response.status_code == 200
    assert brain.tasks.get_next_task() is None
    assert project['id'] not in brain.watcher.get_watched_projects()
    assert brain.watcher.scan_project(project['id'], str(tmp_path)) == []
    assert client.post('/api/ui/ideas/' + idea['id'] + '/qualify', json={'qualification': 'PROJECT'}).status_code in (400, 409)
    # Legacy create/upsert cannot overwrite edits or implicitly resurrect work.
    response = client.post('/api/ui/projects', json={'id': project['id'], 'name': 'Replacement'})
    assert response.status_code in (400, 409)
    assert brain.ledger.data['projects'][0]['archived']


def test_legacy_relationship_and_qualification_updates_preserve_newer_edits(tmp_path):
    from drift.organism import Project
    from drift.pipeline import IdeaPipeline
    brain, _ = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'Example', 'Example'))
    idea = brain.ledger.add_idea('Example project')
    other = DriftLedger(str(tmp_path))
    other.mutate(lambda data: data['ideas'][0].update(text='Example edited elsewhere', revision=1, custom_note='concurrent'))
    pipeline = IdeaPipeline(brain.ledger, brain.tasks, {})
    pipeline.match_project(idea.id)
    persisted = DriftLedger(str(tmp_path)).data['ideas'][0]
    assert persisted['text'] == 'Example edited elsewhere'
    assert persisted['custom_note'] == 'concurrent'
    other.mutate(lambda data: data['ideas'][0].update(custom_note='newer still', revision=2))
    pipeline.qualify_idea(idea.id, 'PARKED')
    persisted = DriftLedger(str(tmp_path)).data['ideas'][0]
    assert persisted['custom_note'] == 'newer still'


def test_archived_entities_never_become_attention_candidates(tmp_path):
    from drift.attention import generate_candidates
    from drift.organism import Project
    brain, client = ready(tmp_path)
    brain.ledger.add_project(Project('one', 'No background work', ''))
    idea = brain.ledger.add_idea('No regenerated qualification')
    for kind, record_id in [('projects', 'one'), ('ideas', idea.id)]:
        assert client.request('DELETE', f'/api/ui/{kind}/{record_id}', json={'confirm': True, 'expected_revision': 0}).status_code == 200
    assert not generate_candidates(brain)
    for kind, record_id in [('projects', 'one'), ('ideas', idea.id)]:
        assert client.post(f'/api/ui/{kind}/{record_id}/restore', json={'confirm': True}).status_code == 200
    assert not generate_candidates(brain), 'restore is not permission for new background inference'


def test_legacy_project_post_cannot_upsert_away_metadata(tmp_path):
    brain, client = ready(tmp_path)
    first = client.post('/api/ui/projects', json={'name': 'Existing', 'repo': 'keep/repo'}).json()['project']
    brain.ledger.mutate(lambda data: data['projects'][0].update(intelligence={'summary': 'keep'}, last_seen_commit='original'))
    response = client.post('/api/ui/projects', json={'id': first['id'], 'name': 'Overwrite'})
    assert response.status_code in (400, 409)
    assert brain.ledger.data['projects'][0]['repo'] == 'keep/repo'
    assert brain.ledger.data['projects'][0]['last_seen_commit'] == 'original'


def test_cors_allows_revisioned_editor_methods_without_broadening_origins(tmp_path):
    import os
    import subprocess
    import sys
    script = '''
from drift.server import app
from fastapi.testclient import TestClient
client = TestClient(app)
for method in ('PATCH', 'DELETE'):
    response = client.options('/api/ui/projects/one', headers={
        'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': method,
        'Access-Control-Request-Headers': 'Authorization,Content-Type'})
    assert response.status_code == 200, response.text
assert client.options('/api/ui/projects/one', headers={
    'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'PATCH'}).status_code != 200
'''
    result = subprocess.run([sys.executable, '-B', '-c', script], env={**os.environ, 'DRIFT_ALLOWED_ORIGINS': 'http://localhost:5173'},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_archive_during_tool_loop_prevents_later_tools_and_followups(tmp_path, monkeypatch):
    import asyncio
    brain, client = ready(tmp_path)
    idea = brain.ledger.add_idea('Stop ongoing idea work')
    task = brain.tasks.create_task('Idea work', 'Understand', idea_id=idea.id)
    calls = []
    def provider(*a, **k):
        return {'text': '', 'output': [], 'tool_calls': [
            {'name': 'read_file', 'arguments': {'path': 'one'}, 'call_id': 'one'},
            {'name': 'read_file', 'arguments': {'path': 'two'}, 'call_id': 'two'}]}
    def tool(name, args, root):
        calls.append(args['path'])
        client.request('DELETE', '/api/ui/ideas/' + idea.id, json={'confirm': True, 'expected_revision': 0})
        return 'read finished'
    monkeypatch.setattr('drift.brain.chat', provider)
    monkeypatch.setattr('drift.brain.execute_tool', tool)
    asyncio.run(brain._think_once())
    assert calls == ['one']
    assert task.status == 'blocked'
