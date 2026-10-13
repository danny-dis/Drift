from pathlib import Path

from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.organism import Project
from drift.server import create_app


def setup(root):
    brain = Brain({'name': 'project'}, str(root / 'box'))
    brain._init_stores()
    project = root / 'repo'
    project.mkdir()
    (project / 'drift.md').write_text('Human-authored notes stay here.\n', encoding='utf-8')
    brain.ledger.add_project(Project('project', 'Project', '', str(project)))
    def update(data):
        data['projects'][0]['intelligence'] = {
            'summary': 'Investigate persistence.', 'verified': False,
            'findings': ['An advisory finding.'], 'challenges': ['A risk.'],
            'alternatives': [], 'questions': ['What survives restart?'],
            'report_paths': ['answers/task-000000.md']}
    brain.ledger.mutate(update)
    return brain, project, TestClient(create_app({'project': brain}))


def test_reading_project_intelligence_does_not_publish_to_repository(tmp_path):
    _, project, client = setup(tmp_path)
    response = client.get('/api/ui/projects/project/intelligence')
    assert response.status_code == 200
    assert response.json()['intelligence']['verified'] is False
    assert (project / 'drift.md').read_text(encoding='utf-8') == 'Human-authored notes stay here.\n'


def test_publish_requires_explicit_confirmation_and_preserves_human_content(tmp_path):
    _, project, client = setup(tmp_path)
    url = '/api/ui/projects/project/intelligence/publish'
    assert client.post(url, json={}).status_code == 400
    response = client.post(url, json={'confirm': True})
    assert response.status_code == 200
    text = (project / 'drift.md').read_text(encoding='utf-8')
    assert 'Human-authored notes stay here.' in text
    assert 'An advisory finding.' in text
    assert 'What survives restart?' in text
    assert 'unverified' in text.lower()


def test_unknown_project_cannot_publish(tmp_path):
    _, _, client = setup(tmp_path)
    assert client.post('/api/ui/projects/missing/intelligence/publish', json={'confirm': True}).status_code == 404
