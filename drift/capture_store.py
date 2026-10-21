"""Lossless raw captures, retained independently of downstream processing."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterator
from uuid import uuid4


MAX_TEXT_LENGTH = 1_000_000
MAX_PAGE_SIZE = 1000
STATUSES = ("captured", "queued", "processed", "needs_review")
_FIELDS = "id, text, created_at, status, idea_id, task_id, report_path, COALESCE(current_text, text) AS current_text, revision, archived"
_UX_FIELDS = _FIELDS


class IdempotencyConflict(ValueError):
    """An existing client intent was retried with different raw text."""


def _identifier(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _limit(value: Any) -> None:
    if type(value) is not int or not 1 <= value <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be an integer between 1 and {MAX_PAGE_SIZE}")


class CaptureStore:
    """One connection per operation; SQLite serializes independent writers.

    Raw text and client intent keys never expire. WAL and FULL synchronous
    commits make successful writes durable; read transactions keep pagination
    counts and rows in the same snapshot. No capture is deleted or content-deduped.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "captures.sqlite3"
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            from drift.capture_init import enable_wal
            enable_wal(db)
            db.execute("PRAGMA synchronous=FULL")
            # Serialize inspection and DDL together across independent openers.
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS captures (
                        id TEXT PRIMARY KEY,
                        text TEXT NOT NULL,
                        client_id TEXT UNIQUE,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'captured'
                            CHECK (status IN ('captured', 'queued', 'processed', 'needs_review')),
                        idea_id TEXT,
                        task_id TEXT,
                        report_path TEXT,
                        summary TEXT NOT NULL DEFAULT ''
                    )
                """)
                db.execute("CREATE INDEX IF NOT EXISTS captures_order ON captures(created_at DESC, id DESC)")
                columns = {row[1] for row in db.execute("PRAGMA table_info(captures)")}
                for name, definition in (("current_text", "TEXT"), ("revision", "INTEGER NOT NULL DEFAULT 0"),
                                         ("archived", "INTEGER NOT NULL DEFAULT 0"),
                                         ("processing_hold", "INTEGER NOT NULL DEFAULT 0")):
                    if name not in columns:
                        db.execute(f"ALTER TABLE captures ADD COLUMN {name} {definition}")
                db.execute("CREATE INDEX IF NOT EXISTS captures_status ON captures(status, created_at DESC, id DESC)")
                db.execute("CREATE INDEX IF NOT EXISTS captures_task ON captures(task_id)")
                db.execute("""CREATE INDEX IF NOT EXISTS captures_pending
                    ON captures(created_at, id) WHERE task_id IS NULL AND status = 'captured'""")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @contextmanager
    def _db(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=30, isolation_level=None)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def capture(self, text: str, client_id: str | None = None) -> dict:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a nonempty string")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"text exceeds {MAX_TEXT_LENGTH} characters; it was not saved")
        if client_id is not None:
            _identifier(client_id, "client_id")
        with self._db(write=True) as db:
            if client_id is not None:
                row = db.execute(
                    f"SELECT {_FIELDS} FROM captures WHERE client_id = ?", (client_id,)
                ).fetchone()
                if row is not None:
                    if row["text"] != text:
                        raise IdempotencyConflict("client_id already used with different text")
                    return {"capture": dict(row), "deduplicated": True}
            capture_id = uuid4().hex
            created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            db.execute(
                "INSERT INTO captures(id, text, client_id, created_at) VALUES (?, ?, ?, ?)",
                (capture_id, text, client_id, created_at),
            )
            row = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            return {"capture": dict(row), "deduplicated": False}

    def list(self, query: str = "", status: str | None = None,
             limit: int = 50, offset: int = 0, include_archived: bool = False) -> dict:
        _limit(limit)
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a nonnegative integer")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if status is not None and status not in STATUSES:
            raise ValueError("unknown capture status")
        clauses, params = [], []
        if not include_archived:
            clauses.append("archived = 0")
        if query:
            # instr treats %, _, backslashes and NUL as literal substring data.
            clauses.append("(instr(text, ?) > 0 OR instr(COALESCE(current_text, text), ?) > 0)")
            params.extend((query, query))
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._db() as db:
            total = db.execute("SELECT COUNT(*) FROM captures" + where, params).fetchone()[0]
            rows = db.execute(
                f"SELECT {_UX_FIELDS} FROM captures{where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return {"captures": [dict(row, archived=bool(row['archived'])) for row in rows], "total": total,
                "has_more": offset + len(rows) < total}

    def get(self, capture_id: str) -> dict | None:
        _identifier(capture_id, "capture_id")
        with self._db() as db:
            row = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def pending(self, limit: int = 20) -> list[dict]:
        _limit(limit)
        with self._db() as db:
            rows = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE archived = 0 AND processing_hold = 0 AND task_id IS NULL AND status = 'captured' "
                "ORDER BY created_at, id LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def revise(self, capture_id: str, *, text: str | None = None,
               archived: bool | None = None, expected_revision: int | None = None) -> dict:
        """Change only owner-editable derivatives; originals and intent keys are immutable."""
        if text is not None and (not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH):
            raise ValueError("text must be nonempty and within the capture limit")
        with self._db(write=True) as db:
            row = db.execute(f"SELECT {_UX_FIELDS} FROM captures WHERE id = ?", (capture_id,)).fetchone()
            if row is None:
                raise KeyError(capture_id)
            if expected_revision is not None and row['revision'] != expected_revision:
                raise IdempotencyConflict("revision conflict")
            db.execute("UPDATE captures SET current_text = ?, archived = ?, revision = revision + 1 WHERE id = ?",
                       (row['current_text'] if text is None else text,
                        row['archived'] if archived is None else int(archived), capture_id))
            if archived is True:
                db.execute('UPDATE captures SET processing_hold = 1 WHERE id = ?', (capture_id,))
            result = dict(db.execute(f"SELECT {_UX_FIELDS} FROM captures WHERE id = ?", (capture_id,)).fetchone())
        result['archived'] = bool(result['archived'])
        return result

    def view(self, capture_id: str) -> dict | None:
        """Expose owner-editable metadata without changing the raw storage contract."""
        with self._db() as db:
            row = db.execute(f"SELECT {_UX_FIELDS} FROM captures WHERE id = ?", (capture_id,)).fetchone()
        return dict(row, archived=bool(row['archived'])) if row is not None else None

    def processing_held(self, capture_id: str) -> bool:
        """Restoring visibility is not permission to stage previously missing parts."""
        with self._db() as db:
            row = db.execute('SELECT processing_hold FROM captures WHERE id = ?', (capture_id,)).fetchone()
        return bool(row and row[0])

    def link(self, capture_id: str, idea_id: str, task_id: str) -> dict:
        for name, value in (("capture_id", capture_id), ("idea_id", idea_id), ("task_id", task_id)):
            _identifier(value, name)
        with self._db(write=True) as db:
            row = db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone()
            if row is None:
                raise KeyError(capture_id)
            if row["task_id"] is not None:
                if row["idea_id"] != idea_id or row["task_id"] != task_id:
                    raise ValueError("capture is already linked to another idea or task")
                return dict(row)
            db.execute(
                "UPDATE captures SET idea_id = ?, task_id = ?, status = 'queued' WHERE id = ?",
                (idea_id, task_id, capture_id),
            )
            return dict(db.execute(
                f"SELECT {_FIELDS} FROM captures WHERE id = ?", (capture_id,)
            ).fetchone())

    def set_status(self, capture_id: str, status: str) -> None:
        """Repair a task-derived status without replacing retained report metadata."""
        _identifier(capture_id, "capture_id")
        if status not in STATUSES:
            raise ValueError("unknown capture status")
        with self._db(write=True) as db:
            db.execute("UPDATE captures SET status = ? WHERE id = ?", (status, capture_id))

    def finish(self, task_id: str, status: str, report_path: str = "", summary: str = "") -> int:
        """Record processing metadata for all linked captures; never change raw text."""
        _identifier(task_id, "task_id")
        if status not in ("processed", "needs_review"):
            raise ValueError("finish status must be processed or needs_review")
        if not isinstance(report_path, str) or not isinstance(summary, str):
            raise ValueError("report_path and summary must be strings")
        with self._db(write=True) as db:
            cursor = db.execute(
                "UPDATE captures SET status = ?, report_path = ?, summary = ? WHERE task_id = ?",
                (status, report_path, summary, task_id),
            )
            return cursor.rowcount
