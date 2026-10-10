from pathlib import Path
from fastapi.testclient import TestClient
from drift.brain import Brain
from drift.server import create_app


def test_owner_can_read_queued_tasks_and_persisted_answer(tmp_path):
    b = Brain({'name':'reports','animal':'crab'},str(tmp_path))
    b._init_stores()
    task = b.tasks.create_task('owner question','explain it')
    client = TestClient(create_app({'reports':b}))
    r = client.get('/api/ui/tasks')
    assert r.status_code == 200 and r.json()['tasks'][0]['id'] == task.id
    f = tmp_path/'answers'/(task.id+'.md');f.parent.mkdir();f.write_text('unverified advisory report',encoding='utf-8')
    b.tasks.update_task(task.id,last_evidence=str(f))
    r = client.get('/api/ui/tasks/'+task.id+'/report')
    assert r.status_code == 200 and r.json()['text'] == 'unverified advisory report'
    outside=tmp_path.parent/'outside-secret.txt';outside.write_text('not allowed',encoding='utf-8')
    b.tasks.update_task(task.id,last_evidence=str(outside))
    assert client.get('/api/ui/tasks/'+task.id+'/report').status_code == 404


def test_research_ui_uses_real_state_and_displays_report():
    src = (Path(__file__).resolve().parents[1]/'frontend/src/DriftApp.tsx').read_text(encoding='utf-8')
    assert 's.state' in src
    assert 'sessionDetail.report' in src
    assert 'sessionDetail.errors' in src
    assert 'data.session' in src
    assert 'pending runtime integration' not in src
    assert 'PR1 lean UI' not in src
    assert '/api/ui/tasks' in src
