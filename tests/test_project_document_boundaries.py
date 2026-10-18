from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from drift.organism import read_drift_md, update_drift_md
from drift.server import create_app


def publish(root):
    update_drift_md(str(root), state='New advisory', findings=['Finding'],
                    challenges=[], alternatives=[])


@pytest.mark.parametrize('link', ['hardlink', 'symlink'])
def test_linked_document_cannot_read_or_modify_outside_file(tmp_path, link):
    project = tmp_path / 'repo'
    project.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('Private outside content', encoding='utf-8')
    target = project / 'drift.md'
    try:
        if link == 'hardlink':
            target.hardlink_to(outside)
        else:
            target.symlink_to(outside)
    except OSError as error:
        pytest.skip(f'{link} unavailable: {type(error).__name__}')
    assert read_drift_md(str(project)) == ''
    with pytest.raises((ValueError, OSError)):
        publish(project)
    assert outside.read_text(encoding='utf-8') == 'Private outside content'


def test_failed_atomic_publish_preserves_original_document(tmp_path):
    target = tmp_path / 'drift.md'
    original = 'Human notes — café\n'
    target.write_text(original, encoding='utf-8')
    with patch('os.replace', side_effect=OSError('synthetic publish interruption')):
        with pytest.raises(OSError):
            publish(tmp_path)
    assert target.read_text(encoding='utf-8') == original
    assert not list(tmp_path.glob('.drift-md-*'))


@pytest.mark.parametrize('url', ['/api/ui/projects/probe/intelligence/publish',
                                 '/api/organism/projects/probe/drift-md'])
def test_linked_publish_returns_a_clear_rejection(tmp_path, url, monkeypatch):
    monkeypatch.delenv('DRIFT_API_TOKEN', raising=False)
    project = tmp_path / 'repo'
    project.mkdir()
    outside = tmp_path / 'outside.txt'
    outside.write_text('Keep outside', encoding='utf-8')
    (project / 'drift.md').hardlink_to(outside)
    record = {'id': 'probe', 'name': 'Probe', 'local_path': str(project),
              'intelligence': {'summary': 'New advisory'}}
    brain = SimpleNamespace(ledger=SimpleNamespace(data={'projects': [record], 'ideas': [], 'events': []}),
                            tasks=object(), env_path=str(tmp_path / 'box'))
    client = TestClient(create_app({'probe': brain}))
    response = client.post(url, json={'confirm': True, 'state': 'New advisory'})
    assert response.status_code == 409
    assert outside.read_text(encoding='utf-8') == 'Keep outside'
