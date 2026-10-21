from tests.test_capture_ux import ready
from drift.organism import Project


def test_mind_map_uses_all_active_canonical_relationships_and_valid_targets(tmp_path):
    brain, client = ready(tmp_path)
    for n in range(15):
        brain.ledger.add_project(Project(f'p{n}', f'Project {n}', ''))
    first = brain.ledger.add_idea('connected idea')
    second = brain.ledger.add_idea('unrelated idea')
    capture = client.post('/api/ui/captures', json={'text': 'original thought'}).json()['capture']
    def link(data):
        data['ideas'][0]['related_projects'] = ['p0']
        # Persisted semantic edges are real; shelf order is not an edge.
        data['mind_map']['edges'].append({'source': first.id, 'target': second.id, 'relation': 'informs'})
    brain.ledger.mutate(link)
    from drift.capture_store import CaptureStore
    CaptureStore(tmp_path).link(capture['id'], first.id, 'task-placeholder')
    result = client.get('/api/ui/mind-map')
    assert result.status_code == 200, result.text
    graph = result.json()
    nodes = {n['id']: n for n in graph['nodes']}
    assert len(nodes) == 18
    assert nodes['i:' + first.id]['target'] == {'section': 'ideas', 'id': first.id}
    assert nodes['c:' + capture['id']]['target'] == {'section': 'inbox', 'id': capture['id']}
    assert {'source': 'i:' + first.id, 'target': 'p:p0', 'relation': 'related_project'} in graph['edges']
    assert {'source': 'i:' + first.id, 'target': 'i:' + second.id, 'relation': 'informs'} in graph['edges']
    assert {'source': 'c:' + capture['id'], 'target': 'i:' + first.id, 'relation': 'derived_idea'} in graph['edges']
    assert len(graph['edges']) == 3
    assert all(e['source'] in nodes and e['target'] in nodes for e in graph['edges'])
    assert client.request('DELETE', '/api/ui/projects/p0', json={'confirm': True, 'expected_revision': 0}).status_code == 200
    after = client.get('/api/ui/mind-map').json()
    assert 'p:p0' not in {n['id'] for n in after['nodes']}
    assert not any(e['target'] == 'p:p0' for e in after['edges'])


def test_archived_thought_does_not_leave_an_active_generated_idea_in_map_or_wiki(tmp_path):
    from drift.intake import stage_captures
    brain, client = ready(tmp_path)
    capture = client.post('/api/ui/captures', json={'text': 'Hide this thought and its generated projection'}).json()['capture']
    stage_captures(brain)
    idea_id = brain.tasks.list_tasks()[0].idea_id
    assert client.request('DELETE', '/api/ui/captures/' + capture['id'], json={'confirm': True, 'expected_revision': 0}).status_code == 200
    graph = client.get('/api/ui/mind-map').json()
    assert 'i:' + idea_id not in {n['id'] for n in graph['nodes']}
    assert not client.get('/api/ui/ideas').json()['ideas']
    assert client.post('/api/ui/wiki/generate', json={'title': 'No archived projection', 'confirm': True}).status_code == 422
