import asyncio
import json
from pathlib import Path

from drift.brain import Brain
from drift.memory import MemoryStream
from drift.organism import Project
from drift.pipeline import capture_idea_unified


def ready(root):
    brain = Brain({'name': 'outcomes'}, str(root))
    brain.stream = MemoryStream(str(root))
    brain._init_stores()
    return brain


def test_finished_idea_updates_advisory_qualification_without_replacing_original(tmp_path):
    brain = ready(tmp_path)
    original = 'What if we use a graph for this half-finished idea?'
    idea, task = capture_idea_unified(brain.ledger, brain.tasks, {}, original)
    answer = json.dumps({'summary': 'Investigate graph-based knowledge.',
                         'qualification': 'RESEARCH', 'concepts': ['knowledge graph']})
    asyncio.run(brain._finish_answer(task, answer))
    record = next(i for i in brain.ledger.data['ideas'] if i['id'] == idea.id)
    assert record['status'] == 'RESEARCH'
    assert record['text'] == original
    assert record['summary'] == 'Investigate graph-based knowledge.'
    assert record['verified'] is False
    assert task.id in record['outcomes']
    assert Path(record['last_evidence']).is_file()


def test_plain_answer_does_not_leave_a_completed_idea_in_captured(tmp_path):
    brain = ready(tmp_path)
    idea, task = capture_idea_unified(brain.ledger, brain.tasks, {}, 'A messy thought about storage')
    asyncio.run(brain._finish_answer(task, 'Consider the tradeoffs. This needs investigation.'))
    record = next(i for i in brain.ledger.data['ideas'] if i['id'] == idea.id)
    assert record['status'] == 'RESEARCH'
    assert record['qualification_source'] == 'advisory outcome; owner may revise'


def test_project_intelligence_is_internal_until_owner_publishes(tmp_path):
    brain = ready(tmp_path / 'box')
    project_path = tmp_path / 'project'
    project_path.mkdir()
    source = project_path / 'application.py'
    source.write_text('original source', encoding='utf-8')
    brain.ledger.add_project(Project('project', 'Project', '', str(project_path)))
    task = brain.tasks.create_task('Review project', 'Identify open questions', project_id='project')
    asyncio.run(brain._finish_answer(task, json.dumps({
        'summary': 'Storage needs an explicit contract.',
        'findings': ['Current behavior needs investigation.'],
        'questions': ['What is the persistence guarantee?']})))
    project = next(p for p in brain.ledger.data['projects'] if p['id'] == 'project')
    assert project['intelligence']['findings'] == ['Current behavior needs investigation.']
    assert project['intelligence']['verified'] is False
    assert task.id in project['intelligence']['tasks']
    assert not (project_path / 'drift.md').exists()
    assert source.read_text(encoding='utf-8') == 'original source'


def test_repeating_completion_does_not_duplicate_a_domain_outcome(tmp_path):
    brain = ready(tmp_path)
    idea, task = capture_idea_unified(brain.ledger, brain.tasks, {}, 'Research local-first storage')
    asyncio.run(brain._finish_answer(task, 'Compare options; no conclusion verified.'))
    asyncio.run(brain._finish_answer(task, 'Compare options; no conclusion verified.'))
    record = next(i for i in brain.ledger.data['ideas'] if i['id'] == idea.id)
    assert list(record['outcomes']) == [task.id]
    events = [e for e in brain.ledger.data['events'] if e['source'] == f'outcome:{task.id}']
    assert len(events) == 1
