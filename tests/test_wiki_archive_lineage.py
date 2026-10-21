"""Archived projections must not re-enter AI context through original captures."""
import pytest
from drift.intake import stage_captures
from drift.organism import Project
from drift.providers import CallBudget
from tests.test_capture_ux import ready


@pytest.mark.parametrize('target', ['project', 'idea', 'capture'])
@pytest.mark.parametrize('lineage', ['both', 'projection-only', 'metadata-only', 'canonical-only'])
def test_global_wiki_excludes_original_of_archived_projection(tmp_path, target, lineage):
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'ARCHIVED_LINEAGE_SENTINEL'}).json()['capture']
    assert stage_captures(brain) == 1
    idea_id = 'thought-' + capture['id']
    brain.ledger.add_project(Project('one', 'Related project', ''))
    brain.ledger.mutate(lambda data: next(i for i in data['ideas'] if i['id'] == idea_id).update(related_projects=['one']))
    if lineage in ('metadata-only', 'canonical-only'):
        brain.ledger.mutate(lambda data: next(i for i in data['ideas'] if i['id'] == idea_id).pop('capture_id', None))
    if lineage in ('projection-only', 'canonical-only'):
        from contextlib import closing
        import sqlite3
        with closing(sqlite3.connect(tmp_path / 'captures.sqlite3')) as db:
            db.execute('UPDATE captures SET idea_id = NULL WHERE id = ?', (capture['id'],))
            db.commit()
    route = ('/api/ui/projects/one' if target == 'project' else
             '/api/ui/captures/' + capture['id'] if target == 'capture' else '/api/ui/ideas/' + idea_id)
    assert client.request('DELETE', route, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    response = client.post('/api/ui/wiki/generate', json={'title': 'Global after removal', 'confirm': True})
    if target == 'project':
        assert response.status_code == 422
        assert not any(task.wiki_page_id for task in brain.tasks.list_tasks())
    else:
        assert response.status_code == 200
        page = next(p for p in brain.ledger.data['wiki_pages'] if p['id'] == response.json()['page']['id'])
        assert not any(source['kind'] == 'thought' for source in page['sources'])
        assert not any('ARCHIVED_LINEAGE_SENTINEL' in source['text'] for source in page['_snapshots'])
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0


@pytest.mark.parametrize('target', ['project', 'idea'])
def test_legacy_thought_only_wiki_is_suppressed_after_archive_without_sweep(tmp_path, target):
    from drift.task import TaskStore
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Legacy retained original'}).json()['capture']
    stage_captures(brain)
    idea_id = 'thought-' + capture['id']
    brain.ledger.add_project(Project('one', 'Source project', ''))
    brain.ledger.mutate(lambda data: next(i for i in data['ideas'] if i['id'] == idea_id).update(related_projects=['one']))
    queued = client.post('/api/ui/wiki/generate', json={'title': 'Legacy thought-only page', 'confirm': True}).json()
    def only_original(data):
        page = next(p for p in data['wiki_pages'] if p['id'] == queued['page']['id'])
        for field in ('sources', '_snapshots', '_source_catalog'):
            page[field] = [source for source in page[field] if source['kind'] == 'thought']
    brain.ledger.mutate(only_original)
    brain.tasks.update_task(queued['task_id'], processing_approval={'thought:' + capture['id']: 0})
    collection, record_id = ('projects', 'one') if target == 'project' else ('ideas', idea_id)
    # Simulate a durable archive followed by process loss before its task sweep.
    brain.ledger.mutate(lambda data: next(i for i in data[collection] if i['id'] == record_id).update(archived=True, processing_hold=True, revision=1))
    restarted = TaskStore(str(tmp_path))
    assert restarted.get_next_task() is None
    held = restarted.get_task(queued['task_id'])
    assert held.archive_hold and held.status == 'blocked'
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0


@pytest.mark.parametrize('projection_backlink', [True, False])
def test_scoped_wiki_retains_active_thought_with_projection_only_linkage(tmp_path, projection_backlink):
    from contextlib import closing
    import sqlite3
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Active scoped original'}).json()['capture']
    stage_captures(brain)
    idea_id = 'thought-' + capture['id']
    brain.ledger.add_project(Project('one', 'Visible project', ''))
    brain.ledger.mutate(lambda data: next(i for i in data['ideas'] if i['id'] == idea_id).update(related_projects=['one']))
    if not projection_backlink:
        brain.ledger.mutate(lambda data: next(i for i in data['ideas'] if i['id'] == idea_id).pop('capture_id', None))
    with closing(sqlite3.connect(tmp_path / 'captures.sqlite3')) as db:
        db.execute('UPDATE captures SET idea_id = NULL WHERE id = ?', (capture['id'],))
        db.commit()
    response = client.post('/api/ui/wiki/generate', json={'title': 'Scoped original retained', 'project_id': 'one', 'confirm': True})
    assert response.status_code == 200
    sources = response.json()['page']['sources']
    assert any(source['kind'] == 'thought' and source['id'] == capture['id'] for source in sources)
    assert CallBudget(str(tmp_path)).status()['daily_calls'] == 0


def test_thought_permission_includes_idea_and_project_lineage(tmp_path):
    from types import SimpleNamespace
    from drift.archive_policy import ArchivePolicy
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Source with a project'}).json()['capture']
    stage_captures(brain)
    idea_id = 'thought-' + capture['id']
    brain.ledger.add_project(Project('one', 'Source project', ''))
    brain.ledger.mutate(lambda data: next(i for i in data['ideas'] if i['id'] == idea_id).update(related_projects=['one']))
    policy = ArchivePolicy(str(tmp_path))
    permission = policy.approval_revisions(SimpleNamespace(capture_id=capture['id']))
    assert permission == {'thought:' + capture['id']: 0, 'idea:' + idea_id: 0, 'project:one': 0}


def test_archived_multipart_original_is_excluded_while_unrelated_work_remains(tmp_path):
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Safe first part. ' * 700 + '\n\nSIBLING_PRIVATE_SENTINEL'}).json()['capture']
    assert stage_captures(brain, max_tasks=100) > 1
    parts = sorted(brain.tasks.list_tasks(), key=lambda task: task.part_index)
    assert 'SIBLING_PRIVATE_SENTINEL' in parts[-1].source_text
    assert all('SIBLING_PRIVATE_SENTINEL' not in task.source_text for task in parts[:-1])
    assert len({task.idea_id for task in parts}) == 1
    route = '/api/ui/ideas/' + parts[-1].idea_id
    assert client.request('DELETE', route, json={'confirm': True, 'expected_revision': 0}).status_code == 200
    brain.ledger.add_idea('Unrelated safe source')
    response = client.post('/api/ui/wiki/generate', json={'title': 'Active sources only', 'confirm': True})
    assert response.status_code == 200
    page = next(p for p in brain.ledger.data['wiki_pages'] if p['id'] == response.json()['page']['id'])
    assert not any(source['kind'] == 'thought' for source in page['sources'])
    assert not any('SIBLING_PRIVATE_SENTINEL' in source['text'] for source in page['_snapshots'])
    assert any(source['kind'] == 'idea' for source in page['sources'])
    assert brain.tasks.get_next_task().id == response.json()['task_id']


def test_archived_projection_cannot_return_through_another_shared_capture_projection(tmp_path):
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'SHARED_PRIVATE_SENTINEL'}).json()['capture']
    stage_captures(brain)
    idea_id = 'thought-' + capture['id']
    def another_projection(data):
        original = next(i for i in data['ideas'] if i['id'] == idea_id)
        data['ideas'].append(dict(original, id='shared-capture-projection', text='Another projection of the same original'))
    brain.ledger.mutate(another_projection)
    assert client.request('DELETE', '/api/ui/ideas/shared-capture-projection', json={'confirm': True, 'expected_revision': 0}).status_code == 200
    brain.ledger.add_idea('Independent safe source')
    response = client.post('/api/ui/wiki/generate', json={'title': 'No shared-capture bypass', 'confirm': True})
    assert response.status_code == 200
    page = next(p for p in brain.ledger.data['wiki_pages'] if p['id'] == response.json()['page']['id'])
    assert not any('SHARED_PRIVATE_SENTINEL' in source['text'] for source in page['_snapshots'])
    assert not any(source['id'] == idea_id for source in page['sources'])
