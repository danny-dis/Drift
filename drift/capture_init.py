"""Bounded recovery for SQLite's journal-mode initialization race."""
import sqlite3
import time


def _execute_before_deadline(db, sql, deadline, clock):
    remaining = deadline - clock()
    if remaining <= 0:
        raise sqlite3.OperationalError('journal initialization deadline exceeded')
    db.execute(f'PRAGMA busy_timeout={max(0, int(remaining * 1000))}')
    return db.execute(sql)


def enable_wal(db, *, attempts=6, pause=time.sleep, clock=time.monotonic):
    deadline = clock() + 30
    failure = None
    for attempt in range(attempts):
        if clock() >= deadline and failure is not None:
            raise failure
        try:
            mode = _execute_before_deadline(db, 'PRAGMA journal_mode', deadline, clock).fetchone()[0]
            if mode.lower() != 'wal':
                _execute_before_deadline(db, 'PRAGMA journal_mode=WAL', deadline, clock).fetchone()
            db.execute('PRAGMA busy_timeout=30000')
            return
        except sqlite3.OperationalError as error:
            busy = getattr(error, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
            busy = busy or str(error) in ('database is locked', 'database table is locked')
            remaining = deadline - clock()
            if not busy or attempt + 1 >= attempts or remaining <= 0:
                raise
            failure = error
            pause(min(remaining, 0.25, 0.02 * 2 ** attempt))
