"""Read/query-count contracts for a single rendered owner request."""
import pytest

from drift.capture_store import CaptureStore
from tests.test_capture_ux import ready


@pytest.mark.parametrize('path', ['/api/ui/ideas', '/api/ui/ideas?include_archived=true', '/api/ui/mind-map'])
def test_capture_backed_views_share_one_policy_snapshot(tmp_path, monkeypatch, path):
    from drift import archive_policy
    brain, client = ready(tmp_path)
    pairs = []
    for n in range(40):
        capture = client.post('/api/ui/captures', json={'text': f'Original {n}'}).json()['capture']
        idea = brain.ledger.add_idea(f'Projection {n}')
        pairs.append((capture['id'], idea.id))
    def link(data):
        by_id = {i['id']: i for i in data['ideas']}
        for cid, iid in pairs:
            by_id[iid]['capture_id'] = cid
    brain.ledger.mutate(link)
    store = CaptureStore(tmp_path)
    for cid, iid in pairs:
        store.link(cid, iid, 'test-only-' + iid)
    hidden_cid, hidden_iid = pairs[0]
    response = client.request('DELETE', '/api/ui/captures/' + hidden_cid,
        json={'confirm': True, 'expected_revision': 0})
    assert response.status_code == 200

    counts = {'policies': 0, 'metadata_queries': 0}
    original_init = archive_policy.ArchivePolicy.__init__
    def counted_init(self, *args, **kwargs):
        counts['policies'] += 1
        return original_init(self, *args, **kwargs)
    monkeypatch.setattr(archive_policy.ArchivePolicy, '__init__', counted_init)
    original_connect = archive_policy.sqlite3.connect
    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        def trace(sql):
            lower = sql.lower()
            if lower.startswith('select') and 'from captures' in lower and 'processing_hold' in lower:
                counts['metadata_queries'] += 1
        connection.set_trace_callback(trace)
        return connection
    monkeypatch.setattr(archive_policy.sqlite3, 'connect', connect)
    response = client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()
    if path.startswith('/api/ui/ideas'):
        records = {i['id']: i for i in data['ideas']}
        if 'include_archived=true' in path:
            assert len(records) == 40 and records[hidden_iid]['archived'] is True
        else:
            assert len(records) == 39 and hidden_iid not in records
    else:
        ids = {node['id'] for node in data['nodes']}
        assert 'i:' + hidden_iid not in ids and 'c:' + hidden_cid not in ids
        assert 'i:' + pairs[-1][1] in ids and 'c:' + pairs[-1][0] in ids
    assert counts == {'policies': 1, 'metadata_queries': 1}
