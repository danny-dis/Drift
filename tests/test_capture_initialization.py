import sqlite3

import pytest

from drift.capture_store import CaptureStore


def test_initial_wal_contention_is_retried_without_losing_the_capture(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    attempts = []
    class Connection:
        def __init__(self, db):
            self.db = db
        def execute(self, sql, *args):
            if sql == 'PRAGMA journal_mode=WAL':
                attempts.append(sql)
                if len(attempts) == 1:
                    raise sqlite3.OperationalError('database is locked')
            return self.db.execute(sql, *args)
        @property
        def row_factory(self):
            return self.db.row_factory
        @row_factory.setter
        def row_factory(self, value):
            self.db.row_factory = value
        def __getattr__(self, name):
            return getattr(self.db, name)
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: Connection(real_connect(*a, **kw)))
    store = CaptureStore(tmp_path)
    result = store.capture('exact original despite startup contention', 'wal-retry')
    assert len(attempts) == 2
    assert store.get(result['capture']['id'])['text'] == 'exact original despite startup contention'


def test_wal_lock_retry_is_bounded_and_other_database_errors_are_not_retried():
    from drift.capture_init import enable_wal
    class Locked:
        calls = 0
        def execute(self, sql):
            self.calls += 1
            raise sqlite3.OperationalError('database is locked')
    db = Locked()
    pauses = []
    with pytest.raises(sqlite3.OperationalError):
        enable_wal(db, attempts=3, pause=pauses.append)
    assert db.calls == 3
    assert len(pauses) == 2
    class Broken(Locked):
        def execute(self, sql):
            self.calls += 1
            raise sqlite3.OperationalError('malformed database')
    db = Broken()
    with pytest.raises(sqlite3.OperationalError, match='malformed'):
        enable_wal(db, pause=pauses.append)
    assert db.calls == 1
