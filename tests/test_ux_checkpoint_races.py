"""Deterministic owner-edit races at background persistence boundaries."""
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event
import sqlite3

import pytest

from drift.organism import DriftLedger, Project
from drift.attention import AttentionEconomy, Candidate
from drift.capture_store import CaptureStore
from drift.task import TaskStore
from drift.watcher import GitChange, GitWatcher


@pytest.fixture
def state(tmp_path):
    root = str(tmp_path)
    ledger = DriftLedger(root)
    ledger.add_project(Project('one', 'Original', 'keep/repo', local_path='old-path',
                               last_seen_commit='old-commit'))
    tasks = TaskStore(root)
    return SimpleNamespace(env_path=root, ledger=ledger, tasks=tasks)


def edit_project(state, **changes):
    DriftLedger(state.env_path).mutate(lambda data: data['projects'][0].update(**changes))


@pytest.mark.parametrize('boundary', ['snapshot', 'collect'])
@pytest.mark.parametrize('edit', ['archive', 'path', 'rename', 'hold', 'remove', 'checkpoint'])
def test_watcher_checkpoint_preserves_concurrent_owner_edit(state, monkeypatch, boundary, edit):
    watcher = GitWatcher(state.ledger, state.tasks, {})
    watcher.register_project('one', 'old-path')
    change = GitChange('one', 'new-commit', 'feat: change', 'author', '', [], '')
    updates = {
        'archive': {'archived': True, 'processing_hold': True},
        'path': {'local_path': 'new-path', 'last_seen_commit': 'new-path-commit'},
        'rename': {'name': 'Renamed'},
        'hold': {'processing_hold': True},
        'checkpoint': {'last_seen_commit': 'newer-commit'},
    }

    def concurrent_edit():
        if edit == 'remove':
            DriftLedger(state.env_path).mutate(lambda data: data['projects'].clear())
        else:
            edit_project(state, **updates[edit], revision=1, custom_note='keep concurrent edit')

    def snapshot(path):
        assert path == 'old-path'
        if boundary == 'snapshot':
            concurrent_edit()
        return {'commit': 'new-commit', 'branch': 'main'}

    def collect(*args):
        if boundary == 'collect':
            concurrent_edit()
        return [change]

    monkeypatch.setattr('drift.watcher.git_snapshot', snapshot)
    monkeypatch.setattr(watcher, '_collect_changes', collect)
    result = watcher.scan_project('one')
    persisted = DriftLedger(state.env_path).data['projects']
    if edit == 'remove':
        assert persisted == []
    else:
        project = persisted[0]
        assert all(project[key] == value for key, value in updates[edit].items())
        assert project['custom_note'] == 'keep concurrent edit'
        assert project['revision'] == 1
        assert project['repo'] == 'keep/repo'
        if edit not in ('path', 'checkpoint'):
            assert project['last_seen_commit'] == ('new-commit' if edit == 'rename' else 'old-commit')
    assert result == ([change] if edit == 'rename' else [])


@pytest.mark.parametrize('updates', [
    {'archived': True}, {'processing_hold': True}, {'local_path': 'new-path'},
])
def test_watcher_refreshes_before_git_io(state, monkeypatch, updates):
    watcher = GitWatcher(state.ledger, state.tasks, {})
    watcher.register_project('one', 'old-path')
    edit_project(state, **updates)

    def forbidden(*args):
        pytest.fail('stale or held projects must not reach Git I/O')

    monkeypatch.setattr('drift.watcher.git_snapshot', forbidden)
    assert watcher.scan_project('one') == []


def test_scan_all_survives_archive_removing_live_watch_entry(state, monkeypatch):
    state.ledger.add_project(Project('two', 'Other', '', local_path='other-path'))
    watcher = GitWatcher(state.ledger, state.tasks, {})
    watcher.register_project('one', 'old-path')
    watcher.register_project('two', 'other-path')
    scanned = []

    def snapshot(path):
        scanned.append(path)
        if path == 'old-path':
            state.ledger.mutate(lambda data: data['projects'][0].update(archived=True))
            watcher._watched.pop('one')
        return {'commit': 'new-commit'}

    monkeypatch.setattr('drift.watcher.git_snapshot', snapshot)
    monkeypatch.setattr(watcher, '_collect_changes', lambda *args: [])
    assert watcher.scan_all() == []
    assert scanned == ['old-path', 'other-path']
    assert DriftLedger(state.env_path).data['projects'][0]['archived'] is True


@pytest.mark.parametrize('boundary', ['create', 'update'])
@pytest.mark.parametrize('edit', ['archive', 'path', 'rename', 'hold', 'remove'])
def test_attention_checkpoint_preserves_concurrent_owner_edit(state, monkeypatch, boundary, edit):
    economy = AttentionEconomy(SimpleNamespace(path=state.env_path + '/receipts.json'))
    candidate = Candidate('project_stale', 'Check stale project: Original', project_id='one',
                          dedup_key='stale_project:one', estimated_cost=.01)
    updates = {
        'archive': {'archived': True, 'processing_hold': True},
        'path': {'local_path': 'new-path'},
        'rename': {'name': 'Renamed'},
        'hold': {'processing_hold': True},
    }
    method = 'create_task' if boundary == 'create' else 'update_task'
    original = getattr(state.tasks, method)
    fired = False

    def concurrent_edit(*args, **kwargs):
        nonlocal fired
        task = original(*args, **kwargs)
        if not fired:
            fired = True
            if edit == 'remove':
                DriftLedger(state.env_path).mutate(lambda data: data['projects'].clear())
            else:
                edit_project(state, **updates[edit], revision=1, custom_note='keep concurrent edit')
        return task

    monkeypatch.setattr(state.tasks, method, concurrent_edit)
    result = economy.create_task_from_candidate(state, candidate)
    persisted = DriftLedger(state.env_path).data['projects']
    if edit == 'remove':
        assert persisted == []
    else:
        project = persisted[0]
        assert all(project[key] == value for key, value in updates[edit].items())
        assert project['revision'] == 1
        assert project['custom_note'] == 'keep concurrent edit'
        assert project['last_round'] is None
        assert project['last_seen_commit'] == 'old-commit'
    assert result is None
    [task] = TaskStore(state.env_path).list_tasks()
    assert task.status == task.phase == 'blocked'
    assert task.archive_hold
    assert task.attempt_count == 0
    assert task.last_evidence == 'attention_dedup_key=stale_project:one'
    assert state.tasks.get_next_task() is None
    assert economy.budget.daily_spend() == economy.budget.weekly_spend() == 0


@pytest.mark.parametrize('kind', ['project', 'idea'])
@pytest.mark.parametrize('flag', ['archived', 'processing_hold', 'missing'])
def test_attention_revalidates_source_before_task_admission(state, kind, flag):
    economy = AttentionEconomy(SimpleNamespace(path=state.env_path + '/receipts.json'))
    if kind == 'idea':
        idea = state.ledger.add_idea('Qualify me')
        collection, record_id = 'ideas', idea.id
        candidate = Candidate('unqualified_idea', 'Qualify idea', dedup_key='idea:' + record_id)
    else:
        collection, record_id = 'projects', 'one'
        candidate = Candidate('project_stale', 'Review project', project_id=record_id)

    def change(data):
        if flag == 'missing':
            data[collection].clear()
        else:
            data[collection][0][flag] = True

    DriftLedger(state.env_path).mutate(change)
    assert economy.create_task_from_candidate(state, candidate) is None
    assert state.tasks.list_tasks() == []


def test_attention_checkpoint_merges_unrelated_concurrent_metadata(state, monkeypatch):
    economy = AttentionEconomy(SimpleNamespace(path=state.env_path + '/receipts.json'))
    original = state.tasks.create_task

    def create(*args, **kwargs):
        task = original(*args, **kwargs)
        edit_project(state, intelligence={'summary': 'concurrent'}, custom_note='keep')
        return task

    monkeypatch.setattr(state.tasks, 'create_task', create)
    candidate = Candidate('git', 'Analyze commit', project_id='one', dedup_key='git:one:commit')
    task = economy.create_task_from_candidate(state, candidate)
    assert task is state.tasks.get_next_task()
    persisted = DriftLedger(state.env_path).data['projects'][0]
    assert persisted['intelligence'] == {'summary': 'concurrent'}
    assert persisted['custom_note'] == 'keep'
    assert persisted['last_seen_commit'] == 'old-commit'
    assert persisted['last_round'] is not None


def test_attention_respects_related_project_archive_before_admission(state):
    idea = state.ledger.add_idea('Qualify me')
    state.ledger.mutate(lambda data: data['ideas'][0].update(related_projects=['one']))
    edit_project(state, archived=True)
    economy = AttentionEconomy(SimpleNamespace(path=state.env_path + '/receipts.json'))
    candidate = Candidate('unqualified_idea', 'Qualify idea', dedup_key='idea:' + idea.id)
    assert economy.create_task_from_candidate(state, candidate) is None
    assert state.tasks.list_tasks() == []


@pytest.mark.parametrize('boundary', ['create', 'update'])
def test_attention_blocks_idea_archived_during_admission(state, monkeypatch, boundary):
    idea = state.ledger.add_idea('Qualify me')
    economy = AttentionEconomy(SimpleNamespace(path=state.env_path + '/receipts.json'))
    candidate = Candidate('unqualified_idea', 'Qualify idea', dedup_key='idea:' + idea.id)
    method = 'create_task' if boundary == 'create' else 'update_task'
    original = getattr(state.tasks, method)
    fired = False

    def archive(*args, **kwargs):
        nonlocal fired
        task = original(*args, **kwargs)
        if not fired:
            fired = True
            DriftLedger(state.env_path).mutate(lambda data: data['ideas'][0].update(archived=True))
        return task

    monkeypatch.setattr(state.tasks, method, archive)
    assert economy.create_task_from_candidate(state, candidate) is None
    [task] = TaskStore(state.env_path).list_tasks()
    assert task.status == 'blocked'
    assert task.archive_hold
    assert state.tasks.get_next_task() is None


@pytest.fixture
def old_captures(tmp_path):
    text = '  Original\r\n\x00 unchanged Ω  '
    path = tmp_path / 'captures.sqlite3'
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute("""CREATE TABLE captures (
            id TEXT PRIMARY KEY, text TEXT NOT NULL, client_id TEXT UNIQUE,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'captured'
                CHECK (status IN ('captured', 'queued', 'processed', 'needs_review')),
            idea_id TEXT, task_id TEXT, report_path TEXT,
            summary TEXT NOT NULL DEFAULT '')""")
        db.execute('CREATE INDEX captures_order ON captures(created_at DESC, id DESC)')
        db.execute('INSERT INTO captures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   ('original-id', text, 'original-client', '2026-01-01', 'queued',
                    'original-idea', 'original-task', 'original-report', 'original-summary'))
        db.commit()
    return tmp_path, text


def test_old_capture_schema_migration_serializes_independent_openers(old_captures, monkeypatch):
    root, text = old_captures
    connect = sqlite3.connect
    first_inspected = Event()
    second_contending = Event()
    connections = []

    class ScheduledConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            # A locked migration's second opener waits at BEGIN. An unlocked
            # migration reaches table_info; freeze both old column snapshots.
            if self.ordinal == 2 and sql == 'BEGIN IMMEDIATE':
                second_contending.set()
            result = super().execute(sql, *args, **kwargs)
            if sql == 'PRAGMA table_info(captures)':
                rows = list(result)
                if self.ordinal == 1:
                    first_inspected.set()
                    assert second_contending.wait(10), 'second opener never reached migration'
                else:
                    second_contending.set()
                return iter(rows)
            return result

    def scheduled_connect(*args, **kwargs):
        db = connect(*args, **kwargs, factory=ScheduledConnection)
        connections.append(db)
        db.ordinal = len(connections)
        return db

    monkeypatch.setattr('drift.capture_store.sqlite3.connect', scheduled_connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(CaptureStore, root)
        assert first_inspected.wait(10), 'first opener never inspected old schema'
        second = pool.submit(CaptureStore, root)
        stores = [first.result(timeout=15), second.result(timeout=15)]
    assert len(connections) == 2
    monkeypatch.setattr('drift.capture_store.sqlite3.connect', connect)
    for store in stores:
        retry = store.capture(text, 'original-client')
        assert retry['deduplicated']
        assert retry['capture']['id'] == 'original-id'
        assert retry['capture']['text'] == retry['capture']['current_text'] == text
        assert retry['capture']['revision'] == retry['capture']['archived'] == 0
        assert retry['capture']['task_id'] == 'original-task'
    with closing(connect(root / 'captures.sqlite3')) as db:
        assert db.execute('SELECT summary, report_path, idea_id, status FROM captures').fetchone() == (
            'original-summary', 'original-report', 'original-idea', 'queued')
        names = [row[1] for row in db.execute('PRAGMA table_info(captures)')]
    assert len(names) == len(set(names)) == 13
    assert set(names) >= {'current_text', 'revision', 'archived', 'processing_hold'}


def test_old_capture_schema_migration_rolls_back_partial_alter(old_captures, monkeypatch):
    root, text = old_captures
    connect = sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.startswith('ALTER TABLE captures ADD COLUMN revision '):
                raise sqlite3.OperationalError('injected migration failure')
            return super().execute(sql, *args, **kwargs)

    monkeypatch.setattr('drift.capture_store.sqlite3.connect',
                        lambda *a, **k: connect(*a, **k, factory=FailingConnection))
    with pytest.raises(sqlite3.OperationalError, match='injected migration failure'):
        CaptureStore(root)
    with closing(connect(root / 'captures.sqlite3')) as db:
        names = {row[1] for row in db.execute('PRAGMA table_info(captures)')}
        assert 'current_text' not in names, 'partial migration must be rolled back'
        assert db.execute('SELECT text, client_id, summary FROM captures').fetchone() == (
            text, 'original-client', 'original-summary')
    monkeypatch.setattr('drift.capture_store.sqlite3.connect', connect)
    assert CaptureStore(root).capture(text, 'original-client')['deduplicated']
