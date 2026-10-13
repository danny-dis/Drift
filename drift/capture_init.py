"""Bounded recovery for SQLite's journal-mode initialization race."""
import sqlite3
import time


def enable_wal(db, *, attempts=6, pause=time.sleep, clock=time.monotonic):
    deadline = clock() + 30
    for attempt in range(attempts):
        try:
            mode = db.execute('PRAGMA journal_mode').fetchone()[0]
            if mode.lower() != 'wal':
                db.execute('PRAGMA journal_mode=WAL').fetchone()
            return
        except sqlite3.OperationalError as error:
            busy = getattr(error, 'sqlite_errorcode', None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
            busy = busy or str(error) in ('database is locked', 'database table is locked')
            if not busy or attempt + 1 >= attempts or clock() >= deadline:
                raise
            pause(min(0.25, 0.02 * 2 ** attempt))
